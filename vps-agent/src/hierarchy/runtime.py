"""In-process multi-bot runtime.

One process owns every bot. Chat and DMs are handled here. Delivery does not
depend on a UI tab, a lease, or another product. Bots drive a real computer
(shell, files, HTTP) on this machine.
"""
from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path

from hierarchy import computer, inbox, tools
from hierarchy.llm import CompleteFn, complete as llm_complete
from dataclasses import replace

from hierarchy.models import Bot, ChatReply
from hierarchy.store import Store

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
        tools.workspace(Path(self.home))

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
            computer.mark_idle(bot_dir, extra_line=f"error: {exc}")
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
        return self._act(bot, instructions, history, text)

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
