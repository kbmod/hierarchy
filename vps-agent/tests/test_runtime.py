from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import hierarchy.runtime as runtime_module
from hierarchy import auth
from hierarchy.runtime import CodexAppError, Runtime


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

    def test_chatgpt_codex_route_persists_thread_and_uses_bot_workdir(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeCodexClient:
            instances: list["FakeCodexClient"] = []

            def __init__(self, **kwargs: object) -> None:
                self.config = kwargs
                self.closed = 0
                self.__class__.instances.append(self)

            def close(self) -> None:
                self.closed += 1

            def run_turn(self, **kwargs: object) -> SimpleNamespace:
                calls.append(kwargs)
                callback = kwargs["on_event"]
                assert callable(callback)
                callback(
                    {
                        "method": "item/started",
                        "params": {
                            "command": "echo token=do-not-display",
                            "error": "authorization=do-not-display",
                            "text": "raw output token=do-not-display",
                            "url": "https://secret.example/token",
                            "status": "running",
                            "item": {"type": "commandExecution", "path": "/tmp/private.txt"},
                        },
                    }
                )
                number = len(calls)
                return SimpleNamespace(
                    thread_id="thread-1",
                    turn_id=f"turn-{number}",
                    status="completed",
                    text=f"codex reply {number}",
                )

        bot = self.rt.create(
            "codex", "Builder", "Works in a private checkout", provider="chatgpt", model="gpt-5.4"
        )
        other = self.rt.create(
            "codex-two", "Reviewer", "Uses the same app server", provider="chatgpt", model="gpt-5.4"
        )
        default = self.rt.create("codex-default", "Reviewer", "Uses Codex default", provider="chatgpt")
        with patch.dict(
            os.environ,
            {
                "HIERARCHY_CHATGPT_BACKEND": "codex",
                "HIERARCHY_CODEX_BIN": "/opt/codex/bin/codex",
                "HIERARCHY_CODEX_HOME": "/var/lib/hierarchy/codex",
            },
            clear=True,
        ), patch.object(runtime_module, "CodexAppClient", FakeCodexClient):
            self.assertEqual(self.rt.chat(bot.id, "first").text, "codex reply 1")
            self.assertEqual(self.rt.chat(bot.id, "second").text, "codex reply 2")
            self.assertEqual(self.rt.chat(other.id, "other bot").text, "codex reply 3")
            self.assertEqual(self.rt.chat(default.id, "default model").text, "codex reply 4")

        workdir = str(Path(self._tmp.name) / "bots" / bot.id / "work")
        self.assertIsNone(calls[0]["thread_id"])
        self.assertEqual(calls[1]["thread_id"], "thread-1")
        self.assertEqual(calls[0]["cwd"], workdir)
        self.assertEqual(calls[0]["model"], "gpt-5.4")
        self.assertIsNone(calls[2]["thread_id"])
        self.assertEqual(calls[2]["cwd"], str(Path(self._tmp.name) / "bots" / other.id / "work"))
        self.assertIsNone(calls[3]["model"])
        self.assertEqual(len(FakeCodexClient.instances), 1)
        state = self.rt.store.codex_state(bot.id)
        self.assertEqual(state["thread_id"], "thread-1")
        self.assertEqual(state["turn_id"], "turn-2")
        self.assertEqual(state["cwd"], workdir)
        self.assertEqual(state["provider"], "chatgpt")
        screen = runtime_module.computer.read(self.rt.store.bot_dir(bot.id))
        self.assertTrue(any("item=commandExecution" in line for line in screen["lines"]))
        self.assertTrue(any("name=private.txt" in line for line in screen["lines"]))
        self.assertFalse(any("do-not-display" in line for line in screen["lines"]))
        self.assertFalse(any("secret.example" in line for line in screen["lines"]))
        self.rt.close()
        self.rt.close()
        self.assertEqual(FakeCodexClient.instances[0].closed, 1)

    def test_codex_error_screen_projection_does_not_include_error_text(self) -> None:
        class FailingCodexClient:
            def __init__(self, **kwargs: object) -> None:
                pass

            def run_turn(self, **kwargs: object) -> None:
                raise runtime_module.CodexAppError(
                    "request failed at https://secret.example/token?access_token=hidden",
                    method="turn/start",
                )

        bot = self.rt.create("error-screen", "Builder", "Safe errors", provider="chatgpt")
        with patch.dict(
            os.environ,
            {
                "HIERARCHY_CHATGPT_BACKEND": "codex",
                "HIERARCHY_CODEX_BIN": "/opt/codex/bin/codex",
                "HIERARCHY_CODEX_HOME": "/var/lib/hierarchy/codex",
            },
            clear=True,
        ), patch.object(runtime_module, "CodexAppClient", FailingCodexClient):
            with self.assertRaisesRegex(runtime_module.CodexAppError, "secret.example"):
                self.rt.chat(bot.id, "fail")
        screen = runtime_module.computer.read(self.rt.store.bot_dir(bot.id))
        self.assertIn("error codex method=turn_start", screen["lines"])
        self.assertFalse(any("secret.example" in line for line in screen["lines"]))

    def test_chatgpt_codex_stale_thread_restarts_once(self) -> None:
        calls: list[object] = []

        class FakeCodexClient:
            def __init__(self, **kwargs: object) -> None:
                self.closed = False

            def run_turn(self, **kwargs: object) -> SimpleNamespace:
                calls.append(kwargs["thread_id"])
                if len(calls) == 1:
                    raise runtime_module.CodexAppError(
                        "thread not found", method="thread/resume", code=-32602
                    )
                return SimpleNamespace(
                    thread_id="fresh-thread",
                    turn_id="turn-fresh",
                    status="completed",
                    text="recovered",
                )

            def close(self) -> None:
                self.closed = True

        bot = self.rt.create("recover", "Builder", "Recovers", provider="chatgpt", model="gpt-5.4")
        self.rt.store.write_codex_state(bot.id, {"thread_id": "expired-thread"})
        with patch.dict(
            os.environ,
            {
                "HIERARCHY_CHATGPT_BACKEND": "codex",
                "HIERARCHY_CODEX_BIN": "/opt/codex/bin/codex",
                "HIERARCHY_CODEX_HOME": "/var/lib/hierarchy/codex",
            },
            clear=True,
        ), patch.object(runtime_module, "CodexAppClient", FakeCodexClient):
            self.assertEqual(self.rt.chat(bot.id, "recover").text, "recovered")
        self.assertEqual(calls, ["expired-thread", None])
        self.assertEqual(self.rt.store.codex_state(bot.id)["thread_id"], "fresh-thread")

    def test_chatgpt_codex_does_not_retry_non_stale_resume_error(self) -> None:
        calls: list[object] = []

        class FakeCodexClient:
            def __init__(self, **kwargs: object) -> None:
                pass

            def run_turn(self, **kwargs: object) -> SimpleNamespace:
                calls.append(kwargs["thread_id"])
                raise runtime_module.CodexAppError(
                    "authentication required", method="thread/resume", code=401
                )

        bot = self.rt.create("no-retry", "Builder", "No retry", provider="chatgpt", model="gpt-5.4")
        self.rt.store.write_codex_state(bot.id, {"thread_id": "thread"})
        with patch.dict(
            os.environ,
            {
                "HIERARCHY_CHATGPT_BACKEND": "codex",
                "HIERARCHY_CODEX_BIN": "/opt/codex/bin/codex",
                "HIERARCHY_CODEX_HOME": "/var/lib/hierarchy/codex",
            },
            clear=True,
        ), patch.object(runtime_module, "CodexAppClient", FakeCodexClient):
            with self.assertRaisesRegex(runtime_module.CodexAppError, "authentication"):
                self.rt.chat(bot.id, "fail")
        self.assertEqual(calls, ["thread"])

    def test_chatgpt_auto_without_codex_configuration_keeps_http_route(self) -> None:
        bot = self.rt.create("http", "Responder", "Uses HTTP", provider="chatgpt", model="gpt-5.4")
        with patch.dict(os.environ, {"HIERARCHY_CHATGPT_BACKEND": "auto"}, clear=True), patch.object(
            runtime_module, "CodexAppClient", side_effect=AssertionError("unexpected Codex route")
        ), patch.object(runtime_module, "llm_complete", return_value="http reply") as complete:
            reply = self.rt.chat(bot.id, "hello")
        self.assertEqual(reply.text, "http reply")
        complete.assert_called_once()

    def test_unset_bot_provider_uses_active_provider_through_hermes(self) -> None:
        bot = self.rt.create("default", "Responder", "Uses active provider")
        auth.set_active(self._tmp.name, "chatgpt")
        hermes = SimpleNamespace(run_turn=unittest.mock.Mock(return_value="agent reply"))
        self.rt._hermes = hermes

        reply = self.rt.chat(bot.id, "hello")

        self.assertEqual(reply.text, "agent reply")
        routed_bot = hermes.run_turn.call_args.args[0]
        self.assertEqual(routed_bot.provider, "chatgpt")

    def test_chatgpt_codex_mode_requires_both_runtime_paths(self) -> None:
        bot = self.rt.create("missing", "Responder", "Needs Codex", provider="chatgpt")
        with patch.dict(os.environ, {"HIERARCHY_CHATGPT_BACKEND": "codex"}, clear=True):
            with self.assertRaisesRegex(CodexAppError, "HIERARCHY_CODEX_BIN"):
                self.rt.chat(bot.id, "hello")


if __name__ == "__main__":
    unittest.main()
