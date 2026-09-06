"""One directory per bot. Nothing is shared across bots."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hierarchy.models import Bot


class Store:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def bot_dir(self, bot_id: str) -> Path:
        path = self.root / "bots" / bot_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_bot(self, bot: Bot) -> None:
        _write_json(
            self.bot_dir(bot.id) / "identity.json",
            {
                "id": bot.id,
                "name": bot.name,
                "job": bot.job,
                "description": bot.description,
                "reports_to": bot.reports_to,
            },
        )
        if not (self.bot_dir(bot.id) / "instructions.md").exists():
            (self.bot_dir(bot.id) / "instructions.md").write_text(
                f"You are {bot.name}, {bot.job}.\n\n{bot.description}\n",
                encoding="utf-8",
            )

    def list_bots(self) -> list[Bot]:
        root = self.root / "bots"
        if not root.exists():
            return []
        bots: list[Bot] = []
        for child in sorted(root.iterdir()):
            identity = child / "identity.json"
            if identity.exists():
                bots.append(_bot_from_dict(_read_json(identity)))
        return bots

    def get(self, bot_id: str) -> Bot:
        path = self.root / "bots" / bot_id / "identity.json"
        if not path.exists():
            raise KeyError(bot_id)
        return _bot_from_dict(_read_json(path))

    def find_by_name(self, name: str) -> Bot | None:
        want = name.strip().lower()
        for bot in self.list_bots():
            if bot.name.lower() == want:
                return bot
        return None

    def instructions(self, bot_id: str) -> str:
        path = self.bot_dir(bot_id) / "instructions.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_instructions(self, bot_id: str, text: str) -> None:
        self.get(bot_id)
        (self.bot_dir(bot_id) / "instructions.md").write_text(text, encoding="utf-8")

    def append(self, bot_id: str, role: str, content: str) -> None:
        path = self.bot_dir(bot_id) / "history.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"role": role, "content": content}) + "\n")

    def history(self, bot_id: str) -> list[dict[str, str]]:
        path = self.bot_dir(bot_id) / "history.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def preview(self, bot_id: str) -> str:
        history = self.history(bot_id)
        if not history:
            return self.get(bot_id).description
        return history[-1]["content"]


def _bot_from_dict(data: dict[str, Any]) -> Bot:
    return Bot(
        id=data["id"],
        name=data["name"],
        job=data["job"],
        description=data["description"],
        reports_to=data.get("reports_to"),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
