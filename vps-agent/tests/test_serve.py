from __future__ import annotations

import os
import stat
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hierarchy import serve
from hierarchy.runtime import Runtime


class AuthApiTests(unittest.TestCase):
    def test_codex_status_uses_public_helper_without_exposing_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "codex")
            with open(binary, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(binary, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            with patch.dict(
                os.environ,
                {
                    "HIERARCHY_CHATGPT_BACKEND": "auto",
                    "HIERARCHY_CODEX_BIN": binary,
                    "HIERARCHY_CODEX_HOME": tmp,
                },
                clear=True,
            ), patch.object(
                serve,
                "codex_app",
                SimpleNamespace(public_status=lambda **kwargs: {"authenticated": True}),
            ):
                status = serve._codex_status()
            self.assertTrue(status["selected"])
            self.assertTrue(status["available"])
            self.assertTrue(status["authenticated"])
            self.assertEqual(status["credentialOwner"], "codex")
            self.assertNotIn("access_token", status)
            self.assertNotIn("refresh_token", status)

    def test_chatgpt_legacy_oauth_is_rejected_unless_http_backend(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HIERARCHY_CHATGPT_BACKEND": "auto",
                "HIERARCHY_SERVICE_USER": "brit",
            },
            clear=True,
        ):
            body = serve._chatgpt_oauth_error("chatgpt")
        assert body is not None
        self.assertIn("Codex app-server", body)
        self.assertIn("HIERARCHY_CHATGPT_BACKEND=http", body)
        self.assertIn("codex login", body)
        with patch.dict(os.environ, {"HIERARCHY_CHATGPT_BACKEND": "http"}, clear=True):
            self.assertIsNone(serve._chatgpt_oauth_error("chatgpt"))

    def test_embedded_page_reflects_codex_status_and_guards_oauth(self) -> None:
        self.assertIn('id="codex-status"', serve._PAGE)
        self.assertIn("ChatGPT via Codex (unavailable)", serve._PAGE)
        self.assertIn('id="bot-provider"', serve._PAGE)
        self.assertIn('id="bot-model"', serve._PAGE)
        self.assertIn("provider: document.getElementById('bot-provider').value || undefined", serve._PAGE)
        self.assertIn("model: document.getElementById('bot-model').value || undefined", serve._PAGE)
        self.assertIn("Default model (leave blank)", serve._PAGE)
        self.assertIn("codex.backend === 'http'", serve._PAGE)
        self.assertIn("button.disabled = !allowed", serve._PAGE)
        self.assertIn("ChatGPT login is owned by Codex", serve._PAGE)

    def test_shutdown_drains_jobs_before_runtime_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(tmp)
            # Construct only the lifecycle surface: binding a listening
            # socket is forbidden in the unit-test sandbox.
            server = object.__new__(serve.Server)
            server.runtime = runtime
            events: list[tuple[str, object]] = []
            server._stop = threading.Event()
            server._httpd = SimpleNamespace(
                shutdown=lambda: events.append(("http_shutdown", None)),
                server_close=lambda: events.append(("http_close", None)),
            )
            server.jobs = SimpleNamespace()
            server.jobs.close = lambda wait=True: events.append(("jobs", wait))  # type: ignore[method-assign]
            runtime.close = lambda: events.append(("runtime", None))  # type: ignore[method-assign]

            server.shutdown()

            self.assertEqual(
                events,
                [("jobs", True), ("http_shutdown", None), ("http_close", None), ("runtime", None)],
            )


if __name__ == "__main__":
    unittest.main()
