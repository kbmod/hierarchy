from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hierarchy.codex_app import (
    CodexAppClient,
    CodexAppError,
    _ProcessIdentity,
    codex_status,
)


class _FakeInput:
    def __init__(self, process: "_FakeProcess") -> None:
        self.process = process
        self.closed = False

    def write(self, value):
        if self.closed:
            raise BrokenPipeError("closed")
        if isinstance(value, bytes):
            value = value.decode()
        self.process.receive(json.loads(value))
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeOutput:
    def __init__(self) -> None:
        self.lines: queue.Queue[object] = queue.Queue()

    def put(self, value: dict) -> None:
        self.lines.put(json.dumps(value) + "\n")

    def readline(self):
        value = self.lines.get()
        return value


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = _FakeOutput()
        self.stderr = _FakeOutput()
        self.stdin = _FakeInput(self)
        self.returncode = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.requests: list[dict] = []
        self._handler = None

    def poll(self):
        return self.returncode

    def receive(self, request: dict) -> None:
        self.requests.append(request)
        if self._handler is not None:
            self._handler(request, self)

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = 0
        self.stdout.lines.put("")
        self.stderr.lines.put("")

    def kill(self) -> None:
        self.kill_calls += 1
        self.terminate()

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


class CodexAppClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.process = _FakeProcess()

        def handler(request, process):
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                process.stdout.put({"id": request_id, "result": {"userAgent": "fake/0.1"}})
            elif method == "thread/start":
                process.stdout.put({"id": request_id, "result": {"thread": {"id": "thread-new"}}})
                process.stdout.put({"method": "thread/started", "params": {"thread": {"id": "thread-new"}}})
            elif method == "thread/resume":
                tid = request["params"]["threadId"]
                process.stdout.put({"id": request_id, "result": {"thread": {"id": tid}}})
            elif method == "turn/start":
                process.stdout.put({"id": request_id, "result": {"turn": {"id": "turn-1"}}})
            elif method == "turn/interrupt":
                process.stdout.put({"id": request_id, "result": {}})

        self.default_handler = handler
        self.process._handler = handler
        self.popen_kwargs: dict[str, object] = {}

        def popen(*args, **kwargs):
            self.popen_kwargs.update(kwargs)
            return self.process

        self.popen = patch("hierarchy.codex_app.subprocess.Popen", side_effect=popen)
        self.popen.start()

    def tearDown(self) -> None:
        self.popen.stop()

    def test_start_performs_initialize_handshake(self) -> None:
        client = CodexAppClient(binary="codex", codex_home="/tmp/codex", timeout=1)
        client.start()
        self.assertEqual(
            [request.get("method") for request in self.process.requests],
            ["initialize", "initialized"],
        )
        initialize = self.process.requests[0]
        self.assertEqual(initialize["params"]["capabilities"], {"experimentalApi": True})
        client.close()

    @unittest.skipUnless(os.name == "posix", "POSIX process sessions only")
    def test_app_server_starts_in_new_process_session(self) -> None:
        client = CodexAppClient(timeout=1)
        client.start()
        self.assertIs(self.popen_kwargs.get("start_new_session"), True)
        client.close()

    def test_normal_close_targets_exact_child_when_group_is_unavailable(self) -> None:
        client = CodexAppClient(timeout=1)
        client.start()
        with patch("hierarchy.codex_app.os.killpg") as killpg:
            client.close()
        killpg.assert_not_called()
        self.assertEqual(self.process.terminate_calls, 1)
        self.assertEqual(self.process.kill_calls, 0)

    @unittest.skipUnless(os.name == "posix", "POSIX process groups only")
    def test_owned_group_gets_term_then_kill_without_guessing(self) -> None:
        client = CodexAppClient(timeout=1)
        client._proc = self.process
        self.process.pid = 424242
        identity = _ProcessIdentity(pid=424242, pgid=424242, starttime=None)
        client._proc_identity = identity
        waits = iter((subprocess.TimeoutExpired("codex", 1), 0))

        def wait(timeout=None):
            value = next(waits)
            if isinstance(value, BaseException):
                raise value
            self.process.returncode = 0
            return value

        self.process.wait = wait
        with patch("hierarchy.codex_app.os.getpgid", return_value=424242), patch(
            "hierarchy.codex_app.os.getpgrp", return_value=31337
        ), patch("hierarchy.codex_app.os.killpg") as killpg:
            client.close()
        self.assertEqual([call.args for call in killpg.call_args_list], [(424242, signal.SIGTERM), (424242, signal.SIGKILL)])
        self.assertEqual(self.process.terminate_calls, 0)
        self.assertEqual(self.process.kill_calls, 0)

    def test_child_environment_is_allowlisted(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HOME": "/home/tester",
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "HIERARCHY_TOKEN": "hierarchy-secret",
                "OPENAI_API_KEY": "provider-secret",
                "TELEGRAM_BOT_TOKEN": "bot-secret",
            },
            clear=True,
        ):
            client = CodexAppClient(
                codex_home="/var/lib/hierarchy/codex",
                timeout=1,
                environment={"HIERARCHY_TOKEN": "override-secret", "TMPDIR": "/tmp/safe"},
            )
            client.start()
        child_env = self.popen_kwargs["env"]
        self.assertEqual(child_env["HOME"], "/home/tester")
        self.assertEqual(child_env["CODEX_HOME"], "/var/lib/hierarchy/codex")
        self.assertEqual(child_env["TMPDIR"], "/tmp/safe")
        self.assertNotIn("HIERARCHY_TOKEN", child_env)
        self.assertNotIn("OPENAI_API_KEY", child_env)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", child_env)
        client.close()

    def test_status_delegates_auth_check_without_returning_output(self) -> None:
        with patch(
            "hierarchy.codex_app.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="signed in as test", stderr=""),
        ) as run:
            client = CodexAppClient(binary="/opt/codex", codex_home="/var/lib/codex", timeout=10)
            status = client.status()
        self.assertEqual(status, {"binary": "/opt/codex", "available": True, "authenticated": True})
        command = run.call_args.args[0]
        self.assertEqual(command, ["/opt/codex", "login", "status"])
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["CODEX_HOME"], "/var/lib/codex")
        self.assertNotIn("HIERARCHY_TOKEN", child_env)

    def test_status_is_cached_for_ten_seconds(self) -> None:
        with patch(
            "hierarchy.codex_app.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ) as run:
            first = codex_status("/cache-test-codex", "/cache-test-home")
            second = codex_status("/cache-test-codex", "/cache-test-home")
        self.assertEqual(first, second)
        run.assert_called_once()

    def test_new_thread_turn_extracts_agent_message_and_completion(self) -> None:
        events: list[dict] = []

        def finish(request, process):
            if request.get("method") != "turn/start":
                return self.default_handler(request, process)
            self.default_handler(request, process)
            process.stdout.put(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-new",
                        "turnId": "turn-1",
                        "item": {"type": "agentMessage", "id": "m1", "text": "done"},
                    },
                }
            )
            process.stdout.put(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-new",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                }
            )

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        result = client.run_turn(None, "/tmp", "gpt-test", "system", "hello", events.append)
        self.assertEqual((result.text, result.status, result.thread_id, result.turn_id), ("done", "completed", "thread-new", "turn-1"))
        self.assertEqual([event["method"] for event in events], ["item/completed", "turn/completed"])
        client.close()

    def test_supplied_unknown_thread_is_resumed(self) -> None:
        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.stdout.put({"method": "turn/completed", "params": {"threadId": "saved", "turn": {"id": "turn-1", "status": "interrupted"}}})

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        result = client.run_turn("saved", "/tmp", "gpt-test", "", "hello")
        methods = [request.get("method") for request in self.process.requests]
        self.assertIn("thread/resume", methods)
        self.assertEqual((result.thread_id, result.status), ("saved", "interrupted"))
        client.close()

    def test_approval_requests_are_declined(self) -> None:
        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.stdout.put({"id": "approval-1", "method": "item/commandExecution/requestApproval", "params": {"command": "rm -rf /"}})
                process.stdout.put({"method": "turn/completed", "params": {"threadId": "thread-new", "turn": {"id": "turn-1", "status": "completed"}}})

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        result = client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        approval_reply = next(request for request in self.process.requests if request.get("id") == "approval-1")
        self.assertEqual(approval_reply["result"], {"decision": "decline"})
        self.assertEqual(result.status, "completed")
        client.close()

    def test_nonretry_error_drains_to_completion_and_thread_noise_is_not_callbacked(self) -> None:
        events: list[dict] = []

        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.stdout.put({"method": "thread/status/changed", "params": {"threadId": "thread-new", "status": {"type": "active"}}})
                process.stdout.put({"method": "future/event", "params": {"threadId": "thread-new", "turn": "malformed"}})
                process.stdout.put({"method": "error", "params": {"threadId": "thread-new", "turnId": "turn-1", "willRetry": False, "error": {}}})
                process.stdout.put({"method": "turn/completed", "params": {"threadId": "thread-new", "turn": {"id": "turn-1", "status": "completed"}}})

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        result = client.run_turn(None, "/tmp", "gpt-test", "", "hello", events.append)
        self.assertEqual(result.status, "failed")
        self.assertEqual([event["method"] for event in events], ["error", "turn/completed"])
        client.close()

    def test_terminal_events_require_matching_thread_and_turn_identity(self) -> None:
        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                for note in (
                    {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "bad"}}},
                    {"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}},
                    {"method": "error", "params": {"threadId": "other", "turnId": "turn-1", "willRetry": False}},
                    {"method": "turn/completed", "params": {"threadId": "other", "turn": {"id": "turn-1", "status": "completed"}}},
                ):
                    process.stdout.put(note)
                process.stdout.put(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-new",
                            "turnId": "turn-1",
                            "item": {"type": "agentMessage", "text": "good"},
                        },
                    }
                )
                process.stdout.put(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-new",
                            "turn": {"id": "turn-1", "status": "completed"},
                        },
                    }
                )

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        result = client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        self.assertEqual(result.text, "good")
        client.close()

    def test_generation_discards_events_from_retired_process(self) -> None:
        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.stdout.put(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-new",
                            "turn": {"id": "turn-1", "status": "completed"},
                        },
                    }
                )

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        client.start()
        client._events.put(
            (
                client._generation - 1,
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-new",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                },
            )
        )
        result = client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        self.assertEqual(result.status, "completed")
        client.close()

    def test_turn_start_failure_retires_process(self) -> None:
        def fail(request, process):
            if request.get("method") == "initialize":
                self.default_handler(request, process)
            elif request.get("method") == "thread/start":
                self.default_handler(request, process)
                process.stdout.put({"id": request["id"], "error": {"code": -32603, "message": "bad turn"}})
            elif request.get("method") == "turn/start":
                process.stdout.put({"id": request["id"], "error": {"code": -32603, "message": "bad turn"}})

        self.process._handler = fail
        client = CodexAppClient(timeout=1)
        with self.assertRaises(CodexAppError):
            client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        self.assertIsNone(client._proc)
        client.close()

    def test_malformed_successful_turn_start_retires_process(self) -> None:
        def malformed(request, process):
            if request.get("method") == "initialize":
                self.default_handler(request, process)
            elif request.get("method") == "thread/start":
                self.default_handler(request, process)
            elif request.get("method") == "turn/start":
                process.stdout.put({"id": request["id"], "result": {"turn": {}}})

        self.process._handler = malformed
        client = CodexAppClient(timeout=1)
        with self.assertRaises(CodexAppError):
            client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        self.assertIsNone(client._proc)
        client.close()

    def test_workspace_policy_and_default_model_override(self) -> None:
        def finish(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.stdout.put(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-new",
                            "turn": {"id": "turn-1", "status": "completed"},
                        },
                    }
                )

        self.process._handler = finish
        client = CodexAppClient(timeout=1)
        client.run_turn(None, "/tmp/bot-work", None, "", "hello")
        thread = next(request for request in self.process.requests if request.get("method") == "thread/start")
        turn = next(request for request in self.process.requests if request.get("method") == "turn/start")
        self.assertNotIn("model", thread["params"])
        self.assertNotIn("model", turn["params"])
        self.assertEqual(thread["params"]["approvalPolicy"], "never")
        self.assertEqual(thread["params"]["sandbox"], "workspace-write")
        self.assertEqual(thread["params"]["runtimeWorkspaceRoots"], ["/tmp/bot-work"])
        self.assertEqual(turn["params"]["approvalPolicy"], "never")
        self.assertEqual(
            turn["params"]["sandboxPolicy"],
            {"type": "workspaceWrite", "writableRoots": ["/tmp/bot-work"], "networkAccess": True},
        )
        client.close()

    def test_timeout_interrupts_then_retires(self) -> None:
        client = CodexAppClient(timeout=0.08)
        with self.assertRaises(CodexAppError) as raised:
            client.run_turn(None, "/tmp", "gpt-test", "", "wait")
        self.assertIn("timed out", str(raised.exception))
        self.assertIn("turn/interrupt", [request.get("method") for request in self.process.requests])
        self.assertIsNone(client._proc)

    def test_dead_child_is_reported(self) -> None:
        def die(request, process):
            self.default_handler(request, process)
            if request.get("method") == "turn/start":
                process.returncode = 1
                process.stdout.lines.put("")

        self.process._handler = die
        client = CodexAppClient(timeout=1)
        with self.assertRaises(CodexAppError) as raised:
            client.run_turn(None, "/tmp", "gpt-test", "", "hello")
        self.assertIn("exited during turn", str(raised.exception))
        client.close()


if __name__ == "__main__":
    unittest.main()
