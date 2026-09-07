"""Install-wide credentials. Keys and OAuth tokens live in ``<home>/auth.json``."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROVIDERS = ("openai", "xai", "openrouter", "chatgpt", "grok")
KEY_PROVIDERS = ("openai", "xai", "openrouter")
OAUTH_PROVIDERS = ("chatgpt", "grok")

DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1"},
    "xai": {"base_url": "https://api.x.ai/v1", "model": "grok-4.5"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4.1-mini"},
    "chatgpt": {"base_url": "https://chatgpt.com/backend-api/codex", "model": "gpt-5.4"},
    "grok": {"base_url": "https://api.x.ai/v1", "model": "grok-4.5"},
}


def auth_path(home: str | Path) -> Path:
    return Path(home) / "auth.json"


def load(home: str | Path) -> dict[str, Any]:
    path = auth_path(home)
    if not path.exists():
        return {"active": "stub", "keys": {}, "oauth": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active": "stub", "keys": {}, "oauth": {}}
    if not isinstance(data, dict):
        return {"active": "stub", "keys": {}, "oauth": {}}
    data.setdefault("active", "stub")
    data.setdefault("keys", {})
    data.setdefault("oauth", {})
    return data


def save(home: str | Path, data: dict[str, Any]) -> None:
    path = auth_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def set_key(home: str | Path, provider: str, api_key: str, *, model: str | None = None) -> dict[str, Any]:
    if provider not in KEY_PROVIDERS:
        raise ValueError(f"unknown key provider {provider!r}")
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("api_key is required")
    data = load(home)
    row = dict(DEFAULTS[provider])
    row.update(data.get("keys", {}).get(provider) or {})
    row["api_key"] = api_key
    if model:
        row["model"] = model.strip()
    data.setdefault("keys", {})[provider] = row
    data["active"] = provider
    save(home, data)
    return public_status(data)


def set_oauth(home: str | Path, provider: str, tokens: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    if provider not in OAUTH_PROVIDERS:
        raise ValueError(f"unknown oauth provider {provider!r}")
    data = load(home)
    row = dict(DEFAULTS[provider])
    row.update(data.get("oauth", {}).get(provider) or {})
    row.update(tokens)
    if model:
        row["model"] = model.strip()
    data.setdefault("oauth", {})[provider] = row
    data["active"] = provider
    save(home, data)
    return public_status(data)


def set_active(home: str | Path, provider: str) -> dict[str, Any]:
    if provider not in ("stub", *PROVIDERS):
        raise ValueError(f"unknown provider {provider!r}")
    data = load(home)
    data["active"] = provider
    save(home, data)
    return public_status(data)


def public_status(data: dict[str, Any] | None = None, home: str | Path | None = None) -> dict[str, Any]:
    if data is None:
        if home is None:
            raise ValueError("home required")
        data = load(home)
    keys = {
        name: {"configured": True, "model": row.get("model"), "base_url": row.get("base_url")}
        for name, row in (data.get("keys") or {}).items()
        if isinstance(row, dict) and row.get("api_key")
    }
    oauth = {}
    for name, row in (data.get("oauth") or {}).items():
        if not isinstance(row, dict):
            continue
        oauth[name] = {
            "configured": bool(row.get("access_token") or row.get("refresh_token")),
            "model": row.get("model"),
            "expires_at": row.get("expires_at"),
        }
    return {"active": data.get("active") or "stub", "keys": keys, "oauth": oauth}


def credential(home: str | Path) -> dict[str, Any] | None:
    """Resolved active credential for a model call, or None → stub replies."""
    data = load(home)
    active = str(data.get("active") or "stub")
    if active == "stub":
        return None
    if active in KEY_PROVIDERS:
        row = (data.get("keys") or {}).get(active)
        if isinstance(row, dict) and row.get("api_key"):
            return {"kind": "key", "provider": active, **row}
    if active in OAUTH_PROVIDERS:
        row = (data.get("oauth") or {}).get(active)
        if isinstance(row, dict) and (row.get("access_token") or row.get("refresh_token")):
            return {"kind": "oauth", "provider": active, **row}
    return None
