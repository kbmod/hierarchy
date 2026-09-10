from __future__ import annotations

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hierarchy import cli


class BotCliTests(unittest.TestCase):
    def test_create_provisions_persistent_hermes_bot(self) -> None:
        created = SimpleNamespace(id="bot-1", name="Forge", provider="chatgpt", model=None)
        runtime = Mock()
        runtime.create.return_value = created
        runtime._hermes = Mock()
        runtime.store.instructions.return_value = "You are Forge."
        output = io.StringIO()

        with patch.object(cli, "Runtime", return_value=runtime), patch("sys.stdout", output):
            result = cli.main([
                "bot", "create", "Forge", "--job", "Builder",
                "--description", "Implements approved work.",
            ])

        self.assertEqual(result, 0)
        runtime.create.assert_called_once_with(
            "Forge", "Builder", "Implements approved work.", reports_to=None,
            provider="chatgpt", model=None,
        )
        runtime._hermes.ensure_bot.assert_called_once_with(created, "You are Forge.")
        self.assertEqual(json.loads(output.getvalue())["id"], "bot-1")
        runtime.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
