"""Named projects the floor can be kicked onto."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def path_for(root: Path) -> Path:
    return root / "projects.json"


def list_projects(root: Path) -> list[dict[str, Any]]:
    path = path_for(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def save_projects(root: Path, rows: list[dict[str, Any]]) -> None:
    path_for(root).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def add_project(root: Path, *, name: str, outcome: str, lead_id: str, bot_ids: list[str]) -> dict[str, Any]:
    rows = list_projects(root)
    row = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "outcome": outcome.strip(),
        "lead_id": lead_id,
        "bot_ids": bot_ids,
        "status": "running",
        "created_at": time.time(),
    }
    rows.append(row)
    save_projects(root, rows)
    return row
