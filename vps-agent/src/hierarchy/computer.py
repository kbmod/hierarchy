"""Per-bot computer screen — a work surface, not a security boundary."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def path_for(bot_dir: Path) -> Path:
    return bot_dir / "computer.json"


def read(bot_dir: Path) -> dict[str, Any]:
    path = path_for(bot_dir)
    if not path.exists():
        return {
            "status": "idle",
            "title": "Desktop",
            "app": "terminal",
            "lines": [],
            "updated_at": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("status", "idle")
    data.setdefault("title", "Desktop")
    data.setdefault("app", "terminal")
    data.setdefault("lines", [])
    data.setdefault("updated_at", 0)
    return data


def write(bot_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    current = read(bot_dir)
    current.update(payload)
    current["updated_at"] = time.time()
    path = path_for(bot_dir)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def mark_working(bot_dir: Path, *, title: str, lines: list[str], app: str = "terminal") -> dict[str, Any]:
    return write(
        bot_dir,
        {
            "status": "working",
            "title": title,
            "app": app,
            "lines": lines[-24:],
        },
    )


def mark_idle(bot_dir: Path, extra_line: str | None = None) -> dict[str, Any]:
    current = read(bot_dir)
    lines = list(current.get("lines") or [])
    if extra_line:
        lines.append(extra_line)
    return write(bot_dir, {"status": "idle", "lines": lines[-24:]})
