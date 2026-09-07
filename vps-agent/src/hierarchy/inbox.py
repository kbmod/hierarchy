"""Per-bot inbox. The runtime process drains it — the UI does not have to be open."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def enqueue(bot_dir: Path, *, sender: str, text: str) -> str:
    folder = bot_dir / "inbox"
    folder.mkdir(parents=True, exist_ok=True)
    item_id = uuid.uuid4().hex
    payload = {
        "id": item_id,
        "sender": sender,
        "text": text,
        "ts": time.time(),
    }
    tmp = folder / f"{item_id}.json.tmp"
    path = folder / f"{item_id}.json"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    return item_id


def claim(bot_dir: Path) -> list[dict[str, Any]]:
    folder = bot_dir / "inbox"
    if not folder.is_dir():
        return []
    claimed: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        taken = path.with_suffix(".claimed")
        try:
            path.replace(taken)
        except FileNotFoundError:
            continue
        try:
            data = json.loads(taken.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            taken.unlink(missing_ok=True)
            continue
        if not isinstance(data, dict) or not str(data.get("text") or "").strip():
            taken.unlink(missing_ok=True)
            continue
        taken.unlink(missing_ok=True)
        claimed.append(data)
    return claimed
