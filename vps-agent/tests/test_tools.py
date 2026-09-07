from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from hierarchy import tools
from hierarchy.runtime import Runtime


class ToolTests(unittest.TestCase):
    def test_parse_last_tool_object(self) -> None:
        text = 'thinking\n{"tool":"shell","cmd":"ls"}\n'
        call = tools.parse_tool(text)
        self.assertEqual(call["tool"], "shell")
        self.assertEqual(call["cmd"], "ls")

    def test_shell_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            tools.workspace(home)
            out = tools.shell("echo hi-from-computer", tools.workspace(home))
            self.assertIn("hi-from-computer", out)
            tools.write_file(tools.workspace(home) / "note.txt", "alpha")
            self.assertIn("alpha", tools.read_file(tools.workspace(home) / "note.txt"))
            listing = tools.list_dir(tools.workspace(home))
            self.assertIn("note.txt", listing)

    def test_tool_loop_runs_shell(self) -> None:
        replies = [
            '{"tool":"shell","cmd":"echo from-tool"}',
            '{"tool":"done","reply":"ran the command"}',
        ]

        def complete(home, bot, instructions, history, text):
            return replies.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime(tmp)
            bot = rt.create("owl", "Ops", "Runs the computer")
            with unittest.mock.patch("hierarchy.runtime.llm_complete", side_effect=complete):
                reply = rt.chat(bot.id, "run a command")
            self.assertEqual(reply.text, "ran the command")
            screen = Path(tmp) / "bots" / bot.id / "computer.json"
            self.assertTrue(screen.exists())
            self.assertIn("from-tool", screen.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
