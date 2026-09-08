from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from hierarchy.store import Store


class StoreTests(unittest.TestCase):
    def test_codex_state_is_per_bot_and_written_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            store_path = store.root / "bots" / "first"
            second = store.root / "bots" / "second"
            # Identity files make the bot IDs valid Store targets.
            store_path.joinpath("identity.json").parent.mkdir(parents=True)
            store_path.joinpath("identity.json").write_text(
                json.dumps({"id": "first", "name": "First", "job": "x", "description": "x"}),
                encoding="utf-8",
            )
            second.joinpath("identity.json").parent.mkdir(parents=True)
            second.joinpath("identity.json").write_text(
                json.dumps({"id": "second", "name": "Second", "job": "x", "description": "x"}),
                encoding="utf-8",
            )
            store.write_codex_state("first", {"thread_id": "t-1", "cwd": "/work", "token": "discard"})
            self.assertEqual(store.codex_state("first"), {"thread_id": "t-1", "cwd": "/work"})
            self.assertEqual(store.codex_state("second"), {})
            mode = stat.S_IMODE((store_path / "codex.json").stat().st_mode)
            self.assertEqual(mode, 0o600)
            self.assertEqual(list(store_path.glob(".codex.json.*.tmp")), [])

    def test_corrupt_codex_state_starts_a_fresh_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            bot_dir = store.root / "bots" / "bot"
            bot_dir.mkdir(parents=True)
            bot_dir.joinpath("identity.json").write_text(
                json.dumps({"id": "bot", "name": "Bot", "job": "x", "description": "x"}),
                encoding="utf-8",
            )
            Path(bot_dir / "codex.json").write_text("{not-json", encoding="utf-8")
            self.assertEqual(store.codex_state("bot"), {})


if __name__ == "__main__":
    unittest.main()
