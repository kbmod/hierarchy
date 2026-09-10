"""In-process multi-bot runtime.

One process owns every bot. Chat and DMs are handled here. Delivery does not
depend on a UI tab, a lease, or another product. Bots drive a real computer
(shell, files, HTTP) on this machine.
"""
from __future__ import annotations

from dataclasses import replace
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from hierarchy import auth, computer, inbox, tools
from hierarchy.llm import CompleteFn, complete as llm_complete
from hierarchy.hermes_runtime import HermesRuntime, HermesRuntimeError

from hierarchy.models import Bot, ChatReply
from hierarchy.store import Store

try:
    from hierarchy.codex_app import CodexAppClient, CodexAppError, CodexTurnResult
except ImportError:  # The adapter is optional until Codex is configured.
    CodexAppClient = None  # type: ignore[assignment,misc]

    class CodexAppError(RuntimeError):
        pass

    CodexTurnResult = Any  # type: ignore[misc,assignment]

MAX_TOOL_STEPS = 12

TOOL_INSTRUCTIONS = """
You are an always-on teammate with a computer on this VPS.
The shared workspace is the computer directory. Use tools to do real work.
Do not claim you ran a command unless you actually called a tool.

To use a tool, reply with ONLY a JSON object (no markdown):
{"tool":"shell","cmd":"ls -la"}
{"tool":"read","path":"README.md"}
{"tool":"write","path":"notes.md","content":"..."}
{"tool":"list","path":"."}
{"tool":"fetch","url":"https://example.com"}
{"tool":"message","to":"Forge","text":"..."}
{"tool":"done","reply":"message for the human"}

When the job is finished or you need the human, use done.
Never take irreversible actions (rm -rf, deploy, send email, post publicly) without asking.
"""


class Runtime:
    def __init__(self, root: str, complete: CompleteFn | None = None) -> None:
        self.store = Store(root)
        self.home = str(self.store.root)
        self._complete = complete
        self._act_depth = threading.local()
        self._codex_lock_guard = threading.Lock()
        self._codex_locks: dict[str, threading.Lock] = {}
        self._codex_clients: dict[tuple[str, str], Any] = {}
        self._codex_closed = False
        self._hermes = HermesRuntime(root) if HermesRuntime.configured() else None
        tools.workspace(Path(self.home))

    def close(self) -> None:
        """Close cached Codex app-server clients; safe to call more than once."""
        with self._codex_lock_guard:
            if self._codex_closed:
                return
            self._codex_closed = True
            clients = list(self._codex_clients.values())
            self._codex_clients.clear()
        for client in clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                # Shutdown is best effort; one broken child must not prevent
                # the remaining cached clients from being closed.
                continue

    def create(
        self,
        name: str,
        job: str,
        description: str,
        *,
        reports_to: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Bot:
        name = name.strip()
        job = job.strip()
        description = description.strip()
        if not name or not job or not description:
            raise ValueError("name, job, and description are required")
        if self.store.find_by_name(name):
            raise ValueError(f"bot {name!r} already exists")
        reports = None
        if reports_to:
            lead = self.store.get(reports_to) if _looks_like_id(reports_to) else self.store.find_by_name(reports_to)
            if lead is None:
                raise ValueError(f"unknown reports_to {reports_to!r}")
            reports = lead.id
        bot = Bot(
            id=str(uuid.uuid4()),
            name=name,
            job=job,
            description=description,
            reports_to=reports,
            provider=_clean_opt(provider),
            model=_clean_opt(model),
        )
        self.store.write_bot(bot)
        return bot

    def update(
        self,
        bot_id: str,
        *,
        job: str | None = None,
        description: str | None = None,
        reports_to: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        clear_reports: bool = False,
    ) -> Bot:
        bot = self.store.get(bot_id)
        reports = bot.reports_to
        if clear_reports:
            reports = None
        elif reports_to:
            lead = self.store.get(reports_to) if _looks_like_id(reports_to) else self.store.find_by_name(reports_to)
            if lead is None:
                raise ValueError(f"unknown reports_to {reports_to!r}")
            reports = lead.id
        updated = replace(
            bot,
            job=job.strip() if job is not None else bot.job,
            description=description.strip() if description is not None else bot.description,
            reports_to=reports,
            provider=_clean_opt(provider) if provider is not None else bot.provider,
            model=_clean_opt(model) if model is not None else bot.model,
        )
        self.store.write_bot(updated)
        return updated

    def roster(self) -> list[dict[str, str | None]]:
        rows: list[dict[str, str | None]] = []
        bots = sorted(
            self.store.list_bots(),
            key=lambda b: (1 if b.reports_to else 0, b.name.lower()),
        )
        for bot in bots:
            screen = computer.read(self.store.bot_dir(bot.id))
            rows.append(
                {
                    "id": bot.id,
                    "name": bot.name,
                    "job": bot.job,
                    "description": bot.description,
                    "preview": self.store.preview(bot.id),
                    "reports_to": bot.reports_to,
                    "provider": bot.provider,
                    "model": bot.model,
                    "status": str(screen.get("status") or "idle"),
                }
            )
        return rows

    def chat(self, bot_id: str, text: str) -> ChatReply:
        bot = self.store.get(bot_id)
        text = text.strip()
        if not text:
            raise ValueError("message is required")
        self.store.append(bot.id, "user", text)
        reply = self.complete_turn(bot.id, text)
        return ChatReply(bot_id=bot.id, text=reply)

    def complete_turn(self, bot_id: str, text: str) -> str:
        bot = self.store.get(bot_id)
        bot_dir = self.store.bot_dir(bot.id)
        computer.mark_working(
            bot_dir,
            title=f"{bot.name}'s screen",
            app="terminal",
            lines=[
                f"$ {bot.name.lower()} — {bot.job}",
                f"# {text[:180]}",
                "working…",
            ],
        )
        try:
            reply = self._say(bot, text)
        except Exception as exc:  # noqa: BLE001
            # The API may return the provider's diagnostic, but the computer
            # screen is user-visible state and must not receive arbitrary
            # exception text (which can contain URLs, arguments, or tokens).
            computer.mark_idle(bot_dir, extra_line=_computer_error_line(exc))
            raise
        self.store.append(bot.id, "assistant", reply)
        computer.mark_idle(bot_dir, extra_line="done.")
        return reply

    def dm(self, *, sender_id: str, to_id: str, text: str) -> ChatReply:
        sender = self.store.get(sender_id)
        target = self.store.get(to_id)
        text = text.strip()
        if not text:
            raise ValueError("message is required")
        if sender.id == target.id:
            raise ValueError("cannot DM self")
        body = f"Message from {sender.name}: {text}"
        inbox.enqueue(self.store.bot_dir(target.id), sender=sender.name, text=body)
        replies = self.drain(target.id)
        return replies[-1] if replies else ChatReply(bot_id=target.id, text="")

    def drain(self, bot_id: str) -> list[ChatReply]:
        bot = self.store.get(bot_id)
        out: list[ChatReply] = []
        for item in inbox.claim(self.store.bot_dir(bot.id)):
            incoming = str(item.get("text") or "").strip()
            if not incoming:
                continue
            self.store.append(bot.id, "user", incoming)
            reply = self.complete_turn(bot.id, incoming)
            out.append(ChatReply(bot_id=bot.id, text=reply))
        return out

    def history(self, bot_id: str) -> list[dict[str, str]]:
        self.store.get(bot_id)
        return self.store.history(bot_id)

    def exec_shell(self, cmd: str, *, bot_id: str | None = None) -> str:
        del bot_id
        home = Path(self.home)
        cwd = tools.workspace(home)
        computer.append_shell(home, f"$ {cmd}", status="working")
        out = tools.shell(cmd, cwd)
        for line in out.splitlines()[:80]:
            computer.append_shell(home, line, status="working")
        computer.append_shell(home, "", status="idle")
        return out

    def _say(self, bot: Bot, text: str) -> str:
        instructions = self.store.instructions(bot.id)
        history = list(self.store.history(bot.id))
        if self._complete is not None:
            return self._complete(bot, instructions, history, text)
        selected_provider = (bot.provider or auth.load(self.home).get("active") or "").strip().lower()
        if self._hermes is not None and selected_provider in {
            "chatgpt", "grok", "openai", "xai", "openrouter"
        }:
            bot_dir = self.store.bot_dir(bot.id)
            routed_bot = bot if bot.provider else replace(bot, provider=selected_provider)

            def on_progress(status: dict[str, Any]) -> None:
                phase = str(status.get("status") or "working").replace("_", " ")
                if phase == "waiting for approval":
                    approval = status.get("approval") if isinstance(status.get("approval"), dict) else {}
                    tool = str(approval.get("tool") or approval.get("tool_name") or "tool")
                    computer.append_line(bot_dir, f"Hermes approval required: {tool}", status="working")
                else:
                    computer.append_line(bot_dir, f"Hermes run: {phase}", status="working")

            return self._hermes.run_turn(routed_bot, instructions, text, on_progress=on_progress)
        if self._use_codex(bot):
            return self._codex_turn(bot, instructions, text)
        return self._act(bot, instructions, history, text)

    def _use_codex(self, bot: Bot) -> bool:
        if (bot.provider or "").strip().lower() != "chatgpt":
            return False
        backend = os.environ.get("HIERARCHY_CHATGPT_BACKEND", "auto").strip().lower() or "auto"
        if backend not in {"auto", "http", "codex"}:
            raise CodexAppError(
                "HIERARCHY_CHATGPT_BACKEND must be one of auto, http, or codex"
            )
        if backend == "http":
            return False
        configured = bool(
            os.environ.get("HIERARCHY_CODEX_BIN", "").strip()
            and os.environ.get("HIERARCHY_CODEX_HOME", "").strip()
        )
        if backend == "codex" and not configured:
            raise CodexAppError(
                "Codex backend requested, but HIERARCHY_CODEX_BIN and "
                "HIERARCHY_CODEX_HOME are both required"
            )
        return configured

    def _codex_lock(self, bot_id: str) -> threading.Lock:
        with self._codex_lock_guard:
            lock = self._codex_locks.get(bot_id)
            if lock is None:
                lock = threading.Lock()
                self._codex_locks[bot_id] = lock
            return lock

    def _codex_turn(self, bot: Bot, instructions: str, text: str) -> str:
        if CodexAppClient is None:
            raise CodexAppError("Codex app-server adapter is not installed")
        bot_dir = self.store.bot_dir(bot.id)
        work_dir = tools.bot_work(Path(self.home), bot.id)
        with self._codex_lock(bot.id):
            state = self.store.codex_state(bot.id)
            client = self._new_codex_client()

            def on_event(event: Any) -> None:
                line = _codex_event_line(event)
                if line:
                    computer.append_line(bot_dir, line, status="working")

            try:
                result: CodexTurnResult = client.run_turn(
                    thread_id=state.get("thread_id") or None,
                    cwd=str(work_dir),
                    model=bot.model,
                    instructions=instructions,
                    text=text,
                    on_event=on_event,
                )
            except CodexAppError as exc:
                if not state.get("thread_id") or not _is_stale_codex_thread_error(exc):
                    raise
                # A persisted thread can disappear after Codex history
                # cleanup.  Retry once as a new thread; auth, transport,
                # timeout, and turn errors must remain visible to the caller.
                result = client.run_turn(
                    thread_id=None,
                    cwd=str(work_dir),
                    model=bot.model,
                    instructions=instructions,
                    text=text,
                    on_event=on_event,
                )
            status = str(_result_value(result, "status") or "completed").lower()
            if status not in {"completed", "success"}:
                raise CodexAppError(f"Codex turn ended with status {status}")
            reply = _codex_result_text(result)
            thread_id = _result_value(result, "thread_id")
            if thread_id:
                self.store.write_codex_state(
                    bot.id,
                    {
                        "thread_id": thread_id,
                        "turn_id": _result_value(result, "turn_id"),
                        "cwd": str(work_dir),
                        "model": bot.model,
                        "provider": bot.provider,
                    },
                )
            return reply

    def _new_codex_client(self) -> Any:
        """Construct the adapter with the explicitly configured runtime paths."""
        binary = os.environ.get("HIERARCHY_CODEX_BIN", "").strip()
        codex_home = os.environ.get("HIERARCHY_CODEX_HOME", "").strip()
        config = (binary, codex_home)
        with self._codex_lock_guard:
            if self._codex_closed:
                raise CodexAppError("Hierarchy runtime is closed")
            client = self._codex_clients.get(config)
            if client is not None:
                return client
            try:
                client = CodexAppClient(binary=binary, codex_home=codex_home)
            except TypeError as exc:
                raise CodexAppError(
                    "Codex app-server adapter has an incompatible constructor"
                ) from exc
            self._codex_clients[config] = client
            return client

    def _act(self, bot: Bot, instructions: str, history: list[dict[str, str]], text: str) -> str:
        depth = getattr(self._act_depth, "n", 0)
        if depth > 2:
            return llm_complete(self.home, bot, instructions, history, text).strip()
        self._act_depth.n = depth + 1
        prompt = (instructions.strip() + "\n" + TOOL_INSTRUCTIONS).strip()
        working = list(history)
        last_user = text
        bot_dir = self.store.bot_dir(bot.id)
        home = Path(self.home)

        def dm(to: str, body: str) -> str:
            target = self.store.find_by_name(to) if not _looks_like_id(to) else None
            if target is None and _looks_like_id(to):
                try:
                    target = self.store.get(to)
                except KeyError:
                    target = None
            if target is None:
                return f"(unknown bot {to})"
            reply = self.dm(sender_id=bot.id, to_id=target.id, text=body)
            return f"{target.name}: {reply.text}"

        try:
            for _ in range(MAX_TOOL_STEPS):
                raw = llm_complete(self.home, bot, prompt, working, last_user)
                call = tools.parse_tool(raw)
                if call is None:
                    return raw.strip()
                name = str(call.get("tool") or "").lower()
                if name in {"done", "reply"}:
                    return str(call.get("reply") or call.get("text") or raw).strip()
                computer.append_line(
                    bot_dir,
                    f"$ {name} {call.get('cmd') or call.get('path') or call.get('url') or call.get('to') or ''}".strip(),
                )
                result = tools.run_tool(home, bot.id, call, dm=dm)
                for line in str(result).splitlines()[:12]:
                    computer.append_line(bot_dir, line)
                working.append({"role": "assistant", "content": raw})
                last_user = f"TOOL_RESULT ({name}):\n{result}"
                working.append({"role": "user", "content": last_user})
            return "I hit the tool-step limit. Check the computer screen and tell me how to continue."
        finally:
            self._act_depth.n = depth


def _looks_like_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f-]{36}", value.strip().lower()))


def _clean_opt(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


_EVENT_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_STATUS_TOKENS = {
    "completed",
    "error",
    "failed",
    "in_progress",
    "interrupted",
    "pending",
    "running",
    "started",
    "success",
    "waiting",
}


def _codex_event_line(event: Any) -> str:
    """Project protocol metadata only; never display command/output arguments."""
    if not isinstance(event, dict):
        return ""
    raw_kind = str(event.get("type") or event.get("method") or event.get("event") or "")
    # App-server methods use a slash separator; normalize that protocol
    # punctuation to a safe marker instead of exposing arbitrary strings.
    kind = raw_kind.strip().replace("/", "_")
    kind = _event_token(kind) or "event"
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    values: list[str] = []
    item_type = _event_token(item.get("type"))
    if item_type:
        values.append(f"item={item_type}")
    status = _status_token(params.get("status") or item.get("status"))
    if status:
        values.append(f"status={status}")
    # A basename can orient the user without exposing command lines, output,
    # URLs, or arbitrary event payloads.  Command fields are intentionally not
    # considered even when they contain a useful-looking path.
    for key in ("filePath", "path", "cwd", "filename"):
        basename = _safe_basename(item.get(key) or params.get(key))
        if basename:
            values.append(f"name={basename}")
            break
    line = "codex " + kind[:80]
    if values:
        line += " " + " ".join(values)
    return line[:240]


def _event_token(value: Any) -> str:
    text = str(value or "").strip()
    return text if _EVENT_TOKEN.fullmatch(text) else ""


def _status_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    return text if text in _STATUS_TOKENS else ""


def _safe_basename(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "://" in text or "\n" in text or "\r" in text:
        return ""
    text = text.replace("\\", "/").rstrip("/")
    basename = text.rsplit("/", 1)[-1]
    return basename[:80] if _EVENT_TOKEN.fullmatch(basename) else ""


def _computer_error_line(exc: BaseException) -> str:
    """Return a bounded, non-secret error marker for the computer screen."""
    kind = _event_token(type(exc).__name__) or "error"
    if isinstance(exc, CodexAppError):
        raw_method = str(getattr(exc, "method", "") or "").strip().replace("/", "_")
        method = _event_token(raw_method)
        return f"error codex method={method}" if method else "error codex"
    if isinstance(exc, HermesRuntimeError):
        return "error hermes"
    return f"error {kind}"


def _result_value(result: Any, field: str) -> Any:
    if isinstance(result, dict):
        return result.get(field)
    return getattr(result, field, None)


def _codex_result_text(result: Any) -> str:
    text = _result_value(result, "text")
    if text is None:
        raise CodexAppError("Codex app-server returned no reply text")
    return str(text).strip()


def _is_stale_codex_thread_error(exc: CodexAppError) -> bool:
    """Return true only for a resume failure that clearly means thread loss."""
    if getattr(exc, "method", None) != "thread/resume":
        return False
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "thread not found",
            "unknown thread",
            "no such thread",
            "thread does not exist",
            "invalid thread",
        )
    )
