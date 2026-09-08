from __future__ import annotations

import threading
import unittest

from hierarchy.jobs import JobBoard


class JobBoardTests(unittest.TestCase):
    def test_close_drains_running_jobs_and_rejects_new_work(self) -> None:
        started = threading.Event()
        release = threading.Event()
        board = JobBoard(workers=1)

        def work() -> str:
            started.set()
            self.assertTrue(release.wait(2))
            return "finished"

        job = board.submit(bot_id="bot", kind="chat", fn=work)
        self.assertTrue(started.wait(2))
        close_done = threading.Event()

        def close() -> None:
            board.close(wait=True)
            close_done.set()

        thread = threading.Thread(target=close)
        thread.start()
        self.assertFalse(close_done.wait(0.05))
        release.set()
        self.assertTrue(close_done.wait(2))
        thread.join(timeout=1)
        row = board.get(job["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "done")
        with self.assertRaisesRegex(RuntimeError, "closed"):
            board.submit(bot_id="bot", kind="chat", fn=lambda: "late")

        # close is intentionally idempotent for server shutdown/finally paths.
        board.close(wait=True)


if __name__ == "__main__":
    unittest.main()
