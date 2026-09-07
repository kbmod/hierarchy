from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hierarchy.runtime import Runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.rt = Runtime(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_two_bots_are_isolated(self) -> None:
        lead = self.rt.create("lead", "Project lead", "Coordinates specialists")
        finance = self.rt.create("finance", "Finance", "Money surfaces", reports_to=lead.id)
        self.rt.store.write_instructions(lead.id, "LEAD-SECRET")
        self.rt.store.append(lead.id, "user", "lead private")
        self.assertIn("LEAD-SECRET", self.rt.store.instructions(lead.id))
        self.assertNotIn("LEAD-SECRET", self.rt.store.instructions(finance.id))
        self.assertIn("lead private", str(self.rt.history(lead.id)))
        self.assertNotIn("lead private", str(self.rt.history(finance.id)))
        self.assertNotEqual(lead.id, finance.id)
        self.assertEqual(finance.reports_to, lead.id)

    def test_chat_reuses_one_history(self) -> None:
        bot = self.rt.create("owl", "Chief of staff", "Routes work")
        first = self.rt.chat(bot.id, "hello")
        second = self.rt.chat(bot.id, "again")
        self.assertIn("owl", first.text)
        hist = self.rt.history(bot.id)
        self.assertEqual([m["role"] for m in hist], ["user", "assistant", "user", "assistant"])
        self.assertEqual(hist[0]["content"], "hello")
        self.assertEqual(hist[2]["content"], "again")
        self.assertIn("again", second.text)

    def test_dm_lands_without_opening_the_target(self) -> None:
        """Delivery must not wait for a live UI session."""
        lead = self.rt.create("lead", "Project lead", "Coordinates")
        finance = self.rt.create("finance", "Finance", "Money", reports_to=lead.id)
        reply = self.rt.dm(sender_id=finance.id, to_id=lead.id, text="drill ack, status=ok")
        self.assertTrue(reply.text)
        hist = self.rt.history(lead.id)
        self.assertEqual(hist[0]["role"], "user")
        self.assertIn("finance", hist[0]["content"].lower())
        self.assertIn("drill ack", hist[0]["content"])
        self.assertEqual(hist[1]["role"], "assistant")
        inbox_dir = Path(self._tmp.name) / "bots" / lead.id / "inbox"
        leftover = list(inbox_dir.glob("*.json")) if inbox_dir.exists() else []
        self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
