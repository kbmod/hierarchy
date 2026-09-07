from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    job: str
    description: str
    reports_to: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class ChatReply:
    bot_id: str
    text: str
