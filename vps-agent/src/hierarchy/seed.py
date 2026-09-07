"""Default Grok-Bot-style floor. Created once when the store is empty."""
from __future__ import annotations

from hierarchy.models import Bot
from hierarchy.runtime import Runtime

FLOOR: list[tuple[str, str, str, str | None]] = [
    (
        "Atlas",
        "Chief of Staff",
        "You are the operator's chief of staff. Assign outcomes, not task lists. "
        "Coordinate Forge, Scout, and Quill. Summarize handoffs. Never take irreversible "
        "actions, never send external messages, and never change production without asking.",
        None,
    ),
    (
        "Forge",
        "Engineer",
        "You write, review, and ship software on the shared computer. Prefer small diffs, "
        "tests, and a short summary of what changed. Never push, deploy, or delete data "
        "without asking. Report blockers to Atlas.",
        "Atlas",
    ),
    (
        "Scout",
        "Researcher",
        "You find sources, verify claims, and cite them. Separate evidence from hypothesis. "
        "Never invent links. Return the highest-impact finding first. Hand unfinished threads to Atlas.",
        "Atlas",
    ),
    (
        "Quill",
        "Writer",
        "You draft in the operator's voice. Never publish, post, or email without asking. "
        "Keep drafts in the shared workspace. Flag anything that needs a human review.",
        "Atlas",
    ),
]


def ensure_floor(runtime: Runtime) -> list[Bot]:
    existing = {bot.name.lower(): bot for bot in runtime.store.list_bots()}
    created: list[Bot] = []
    for name, job, description, reports in FLOOR:
        if name.lower() in existing:
            created.append(existing[name.lower()])
            continue
        lead = reports
        if lead and lead.lower() in existing:
            lead = existing[lead.lower()].id
        bot = runtime.create(name, job, description, reports_to=lead)
        existing[name.lower()] = bot
        created.append(bot)
    return created
