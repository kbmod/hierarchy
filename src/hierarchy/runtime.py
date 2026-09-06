"""In-process multi-bot runtime.

One process owns every bot. Chat and DMs are handled here. Delivery does not
depend on a UI tab, a lease, or another product.
"""
from __future__ import annotations

import re
import uuid

from hierarchy import inbox
from hierarchy.llm import CompleteFn, complete as llm_complete
from hierarchy.models import Bot, ChatReply
from hierarchy.store import Store


class Runtime:
    def __init__(self, root: str, complete: CompleteFn | None = None) -> None:
        self.store = Store(root)
        self.home = str(self.store.root)
        self._complete = complete

    def create(
        self,
        name: str,
        job: str,
        description: str,
        *,
        reports_to: str | None = None,
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
        )
        self.store.write_bot(bot)
        return bot

    def roster(self) -> list[dict[str, str | None]]:
        rows: list[dict[str, str | None]] = []
        for bot in self.store.list_bots():
            rows.append(
                {
                    "id": bot.id,
                    "name": bot.name,
                    "job": bot.job,
                    "description": bot.description,
                    "preview": self.store.preview(bot.id),
                    "reports_to": bot.reports_to,
                }
            )
        return rows

    def chat(self, bot_id: str, text: str) -> ChatReply:
        bot = self.store.get(bot_id)
        text = text.strip()
        if not text:
            raise ValueError("message is required")
        self.store.append(bot.id, "user", text)
        reply = self._say(bot, text)
        self.store.append(bot.id, "assistant", reply)
        return ChatReply(bot_id=bot.id, text=reply)

    def dm(self, *, sender_id: str, to_id: str, text: str) -> ChatReply:
        """Deliver a message into ``to_id`` and run that bot immediately."""
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
            reply = self._say(bot, incoming)
            self.store.append(bot.id, "assistant", reply)
            out.append(ChatReply(bot_id=bot.id, text=reply))
        return out

    def history(self, bot_id: str) -> list[dict[str, str]]:
        self.store.get(bot_id)
        return self.store.history(bot_id)

    def _say(self, bot: Bot, text: str) -> str:
        instructions = self.store.instructions(bot.id)
        history = self.store.history(bot.id)
        if self._complete is not None:
            return self._complete(bot, instructions, history, text)
        return llm_complete(self.home, bot, instructions, history, text)


def _looks_like_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f-]{36}", value.strip().lower()))
