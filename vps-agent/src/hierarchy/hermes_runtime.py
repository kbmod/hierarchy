"""Thin control-plane client for the upstream Hermes Bot/Gateway runtime.

Hierarchy owns the mobile API and bot roster.  Hermes owns autonomous turns,
tools, memory, approvals, delegation, and durable agent sessions.  One
Hierarchy bot maps to one Bot-Mode-managed Hermes profile and its canonical
``Bot Chat`` session.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from hierarchy.http import HttpError, request
from hierarchy.models import Bot


class HermesRuntimeError(RuntimeError):
    """A controlled Hermes installation, transport, or run failure."""


@dataclass(frozen=True)
class HermesBotState:
    profile: str
    session_id: str
    api_key: str


ProgressFn = Callable[[dict[str, Any]], None]


_PROFILE_SAFE = re.compile(r"[^a-z0-9_-]+")
_PROVIDERS = {
    "chatgpt": "openai-codex",
    "grok": "xai-oauth",
    "openai": "openai-api",
    "xai": "xai",
    "openrouter": "openrouter",
}


class HermesRuntime:
    def __init__(
        self,
        hierarchy_home: str | Path,
        *,
        binary: str | None = None,
        hermes_home: str | Path | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.hierarchy_home = Path(hierarchy_home)
        self.binary = binary or os.environ.get("HIERARCHY_HERMES_BIN", "").strip()
        configured_home = str(hermes_home or os.environ.get("HIERARCHY_HERMES_HOME", "")).strip()
        self.hermes_home = Path(configured_home) if configured_home else Path.home() / ".hermes"
        self.base_url = (base_url or os.environ.get("HIERARCHY_HERMES_URL", "http://127.0.0.1:8642")).rstrip("/")
        self.timeout = timeout or float(os.environ.get("HIERARCHY_HERMES_TURN_TIMEOUT", "3600"))

    @classmethod
    def configured(cls) -> bool:
        backend = os.environ.get("HIERARCHY_AGENT_BACKEND", "auto").strip().lower() or "auto"
        if backend not in {"auto", "hermes", "legacy"}:
            raise HermesRuntimeError("HIERARCHY_AGENT_BACKEND must be auto, hermes, or legacy")
        if backend == "legacy":
            return False
        available = bool(os.environ.get("HIERARCHY_HERMES_BIN", "").strip())
        if backend == "hermes" and not available:
            raise HermesRuntimeError("Hermes backend selected but HIERARCHY_HERMES_BIN is not configured")
        return available

    def ensure_bot(self, bot: Bot, instructions: str) -> HermesBotState:
        state = self._read_state(bot.id)
        if state is not None and self._profile_dir(state.profile).is_dir():
            self._sync_profile(bot, instructions, state)
            self._ensure_session(state)
            return state

        if not self.binary or not os.path.isfile(self.binary) or not os.access(self.binary, os.X_OK):
            raise HermesRuntimeError("Hermes runtime binary is unavailable")
        profile = self._profile_name(bot)
        profile_dir = self._profile_dir(profile)
        if not profile_dir.exists():
            self._run_cli(
                "profile", "create", profile, "--no-alias", "--no-skills",
                "--description", self._profile_description(bot),
            )
        state = HermesBotState(profile=profile, session_id="", api_key=secrets.token_urlsafe(32))
        self._sync_profile(bot, instructions, state)
        state = HermesBotState(profile=profile, session_id=self._ensure_session(state), api_key=state.api_key)
        self._write_state(bot.id, state)
        return state

    def run_turn(
        self,
        bot: Bot,
        instructions: str,
        text: str,
        *,
        on_progress: ProgressFn | None = None,
    ) -> str:
        state = self.ensure_bot(bot, instructions)
        body: dict[str, Any] = {
            "input": text,
            "session_id": state.session_id,
            "instructions": instructions,
        }
        provider = self.provider_for(bot.provider)
        if provider:
            body["provider"] = provider
        if bot.model:
            body["model"] = bot.model
        run = self._json("POST", state, "/v1/runs", body, idempotency_key=secrets.token_hex(16))
        run_id = str(run.get("run_id") or "") if isinstance(run, dict) else ""
        if not run_id:
            raise HermesRuntimeError("Hermes did not return a run id")
        deadline = time.monotonic() + self.timeout
        previous_status = ""
        while time.monotonic() < deadline:
            status = self._json("GET", state, f"/v1/runs/{urllib.parse.quote(run_id, safe='')}")
            phase = str(status.get("status") or "") if isinstance(status, dict) else ""
            if on_progress is not None and (phase != previous_status or phase == "waiting_for_approval"):
                on_progress(status if isinstance(status, dict) else {"status": phase})
            previous_status = phase
            if phase == "completed":
                return str(status.get("output") or "").strip()
            if phase in {"failed", "cancelled"}:
                detail = str(status.get("error") or f"Hermes run {phase}")
                raise HermesRuntimeError(detail)
            time.sleep(0.5 if phase in {"queued", "running"} else 1.0)
        try:
            self._json("POST", state, f"/v1/runs/{urllib.parse.quote(run_id, safe='')}/stop", {})
        except HermesRuntimeError:
            pass
        raise HermesRuntimeError(f"Hermes turn exceeded {int(self.timeout)} seconds")

    def status(self) -> dict[str, Any]:
        auth_status = self.auth_status()
        try:
            _, body = request("GET", f"{self.base_url}/health", timeout=5)
        except Exception as exc:  # noqa: BLE001
            return {
                "configured": bool(self.binary), "available": False,
                "authenticated": auth_status, "error": type(exc).__name__,
            }
        return {
            "configured": bool(self.binary), "available": True,
            "authenticated": auth_status, "health": body,
        }

    def import_oauth(self, provider: str, tokens: dict[str, Any]) -> None:
        """Copy a completed mobile OAuth grant into Hermes's private store."""
        mapped = self.provider_for(provider)
        if mapped not in {"openai-codex", "xai-oauth"}:
            raise HermesRuntimeError(f"Hermes OAuth import does not support {provider!r}")
        payload = {"action": "import", "provider": mapped, "tokens": tokens}
        self._auth_helper(payload)

    def auth_status(self) -> dict[str, bool]:
        if not self.binary:
            return {"chatgpt": False, "grok": False}
        result = self._auth_helper({"action": "status"})
        return {
            "chatgpt": bool(result.get("openai-codex")),
            "grok": bool(result.get("xai-oauth")),
        }

    @staticmethod
    def provider_for(provider: str | None) -> str | None:
        clean = (provider or "").strip().lower()
        return _PROVIDERS.get(clean, clean or None)

    def _ensure_session(self, state: HermesBotState) -> str:
        if state.session_id:
            try:
                self._json("GET", state, f"/api/sessions/{urllib.parse.quote(state.session_id, safe='')}")
                return state.session_id
            except HermesRuntimeError:
                pass
        listing = self._json("GET", state, "/api/sessions?limit=200&title=Bot%20Chat&include_hidden=1")
        for row in listing.get("data") or []:
            if isinstance(row, dict) and str(row.get("title") or "") == "Bot Chat":
                return str(row.get("id") or "")
        created = self._json(
            "POST", state, "/api/sessions",
            {"title": "Bot Chat", "source": "hierarchy_bot", "pinned": True},
        )
        row = created.get("session") if isinstance(created, dict) else None
        session_id = str((row or {}).get("id") or "")
        if not session_id:
            raise HermesRuntimeError("Hermes did not create the canonical Bot Chat")
        return session_id

    def _sync_profile(self, bot: Bot, instructions: str, state: HermesBotState) -> None:
        profile_dir = self._profile_dir(state.profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        control_help = """

## Persistent specialist roster
You are a member of a persistent multi-agent Hierarchy. When the user asks you
to create specialists, do it with the terminal command below; do not merely
describe a proposed roster and do not substitute ephemeral subagents.

`hierarchy-bot create NAME --job ROLE --description DESCRIPTION --provider chatgpt`

Use `hierarchy-bot list` to inspect the live roster. Use
`hierarchy-bot message --from YOUR_NAME --to TARGET --text MESSAGE` to assign
work to a persistent specialist and receive its response. Newly created Bots
also become Hermes Bot Mode teammates with their own SOUL, memory, tools, and
canonical Bot Chat.
"""
        (profile_dir / "SOUL.md").write_text(
            instructions.strip() + control_help.rstrip() + "\n", encoding="utf-8"
        )
        (profile_dir / "profile.yaml").write_text(
            "description: " + json.dumps(self._profile_description(bot)) + "\n"
            "ui_meta:\n"
            "  hermes-bots:\n"
            "    title: " + json.dumps(bot.name) + "\n"
            "    pinned: true\n",
            encoding="utf-8",
        )
        self._merge_env(profile_dir / ".env", "API_SERVER_KEY", state.api_key)
        self._sync_provider_secret(profile_dir / ".env", bot.provider)
        config = profile_dir / "config.yaml"
        current = config.read_text(encoding="utf-8") if config.exists() else ""
        managed_start = "# hierarchy-managed-model\n"
        if managed_start in current:
            current = current.split(managed_start, 1)[0].rstrip() + "\n"
        provider = self.provider_for(bot.provider)
        if provider or bot.model:
            current += managed_start + "model:\n"
            if provider:
                current += f"  provider: {provider}\n"
            if bot.model:
                current += f"  default: {json.dumps(bot.model)}\n"
            current += "terminal:\n"
            current += f"  cwd: {json.dumps(str(self.hierarchy_home / 'computer'))}\n"
        config.write_text(current, encoding="utf-8")

    def _json(
        self,
        method: str,
        state: HermesBotState,
        suffix: str,
        body: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        prefix = f"/p/{urllib.parse.quote(state.profile, safe='')}"
        headers = {"Authorization": f"Bearer {state.api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            _, payload = request(
                method, self.base_url + prefix + suffix,
                json_body=body if method != "GET" else None,
                headers=headers, timeout=30,
            )
            return payload
        except HttpError as exc:
            detail = exc.body[:400]
            try:
                parsed = json.loads(exc.body)
                error = parsed.get("error") if isinstance(parsed, dict) else None
                if isinstance(error, dict):
                    detail = str(error.get("message") or detail)
                elif error:
                    detail = str(error)
            except ValueError:
                pass
            raise HermesRuntimeError(f"Hermes HTTP {exc.status}: {detail}") from exc
        except OSError as exc:
            raise HermesRuntimeError(f"Hermes gateway is unavailable: {exc}") from exc

    def _run_cli(self, *args: str) -> None:
        env = {**os.environ, "HERMES_HOME": str(self.hermes_home)}
        completed = subprocess.run(
            [self.binary, *args], env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "profile creation failed").strip()
            raise HermesRuntimeError(detail[-800:])

    def _auth_helper(self, payload: dict[str, Any]) -> dict[str, Any]:
        python = str(Path(self.binary).with_name("python")) if self.binary else ""
        if not python or not os.path.isfile(python) or not os.access(python, os.X_OK):
            raise HermesRuntimeError("Hermes Python runtime is unavailable")
        script = r'''
import json, sys
from hermes_cli.auth import get_codex_auth_status, get_xai_oauth_auth_status, _save_codex_tokens
from hermes_cli.auth_xai import _save_xai_oauth_tokens

payload = json.load(sys.stdin)
if payload.get("action") == "status":
    result = {
        "openai-codex": bool(get_codex_auth_status().get("logged_in")),
        "xai-oauth": bool(get_xai_oauth_auth_status().get("logged_in")),
    }
elif payload.get("action") == "import":
    provider, tokens = payload.get("provider"), payload.get("tokens") or {}
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise ValueError("OAuth grant must contain access and refresh tokens")
    if provider == "openai-codex":
        _save_codex_tokens(tokens)
    elif provider == "xai-oauth":
        _save_xai_oauth_tokens(tokens, set_active=False)
    else:
        raise ValueError("unsupported provider")
    result = {"ok": True}
else:
    raise ValueError("unsupported action")
json.dump(result, sys.stdout)
'''
        env = {**os.environ, "HERMES_HOME": str(self.hermes_home)}
        completed = subprocess.run(
            [python, "-c", script], input=json.dumps(payload), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "Hermes auth operation failed").strip()
            raise HermesRuntimeError(detail[-800:])
        try:
            result = json.loads(completed.stdout)
        except ValueError as exc:
            raise HermesRuntimeError("Hermes auth helper returned invalid data") from exc
        return result if isinstance(result, dict) else {}

    def _profile_dir(self, profile: str) -> Path:
        return self.hermes_home / "profiles" / profile

    @staticmethod
    def _profile_name(bot: Bot) -> str:
        readable = _PROFILE_SAFE.sub("-", bot.name.lower()).strip("-_")[:24] or "bot"
        return f"hierarchy-{readable}-{bot.id.replace('-', '')[:8]}"

    @staticmethod
    def _profile_description(bot: Bot) -> str:
        return " ".join(f"{bot.job}. {bot.description}".split())[:400]

    def _state_path(self, bot_id: str) -> Path:
        return self.hierarchy_home / "bots" / bot_id / "hermes.json"

    def _read_state(self, bot_id: str) -> HermesBotState | None:
        try:
            row = json.loads(self._state_path(bot_id).read_text(encoding="utf-8"))
            profile, session_id, api_key = (str(row.get(k) or "") for k in ("profile", "session_id", "api_key"))
            if profile and api_key:
                return HermesBotState(profile, session_id, api_key)
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _write_state(self, bot_id: str, state: HermesBotState) -> None:
        path = self._state_path(bot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.__dict__, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        os.chmod(path, 0o600)

    @staticmethod
    def _merge_env(path: Path, key: str, value: str) -> None:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        clean = [line for line in lines if not line.startswith(key + "=")]
        clean.append(f"{key}={value}")
        path.write_text("\n".join(clean) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def _sync_provider_secret(self, path: Path, provider: str | None) -> None:
        env_keys = {
            "openai": "OPENAI_API_KEY",
            "xai": "XAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        managed = set(env_keys.values())
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines = [line for line in lines if line.split("=", 1)[0] not in managed]
        selected = (provider or "").strip().lower()
        env_key = env_keys.get(selected)
        if env_key:
            try:
                data = json.loads((self.hierarchy_home / "auth.json").read_text(encoding="utf-8"))
                row = (data.get("keys") or {}).get(selected) or {}
                api_key = str(row.get("api_key") or "").strip()
            except (OSError, ValueError, TypeError):
                api_key = ""
            if api_key:
                lines.append(f"{env_key}={api_key}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
