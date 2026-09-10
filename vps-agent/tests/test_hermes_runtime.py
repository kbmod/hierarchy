from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hierarchy.hermes_runtime import HermesBotState, HermesRuntime
from hierarchy.models import Bot


class HermesRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.binary = self.root / "hermes-bin"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.python = self.root / "python"
        self.python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.python.chmod(0o755)
        self.client = HermesRuntime(
            self.root / "hierarchy", binary=str(self.binary),
            hermes_home=self.root / "hermes", base_url="http://127.0.0.1:8642", timeout=5,
        )
        self.bot = Bot("12345678-1234-1234-1234-123456789abc", "Owl", "Chief", "Coordinates", provider="chatgpt", model="gpt-5.4")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_profile_is_bot_mode_managed_and_secret_state_is_private(self) -> None:
        profile = self.client._profile_name(self.bot)
        profile_dir = self.client._profile_dir(profile)
        profile_dir.mkdir(parents=True)
        state = HermesBotState(profile, "session-1", "secret-key")
        self.client._sync_profile(self.bot, "You are Owl.", state)
        self.client._write_state(self.bot.id, state)

        self.assertIn("hermes-bots", (profile_dir / "profile.yaml").read_text())
        self.assertIn("provider: openai-codex", (profile_dir / "config.yaml").read_text())
        self.assertIn("default: \"gpt-5.4\"", (profile_dir / "config.yaml").read_text())
        self.assertIn("hierarchy-bot create", (profile_dir / "SOUL.md").read_text())
        self.assertEqual(oct((self.client._state_path(self.bot.id).stat().st_mode) & 0o777), "0o600")
        self.assertEqual(self.client._read_state(self.bot.id), state)

    def test_run_uses_profile_route_canonical_session_and_provider_mapping(self) -> None:
        profile = self.client._profile_name(self.bot)
        self.client._profile_dir(profile).mkdir(parents=True)
        state = HermesBotState(profile, "bot-chat", "secret-key")
        self.client._write_state(self.bot.id, state)
        calls: list[tuple[str, str, dict | None, dict]] = []
        responses = iter([
            (200, {"session": {"id": "bot-chat"}}),
            (202, {"run_id": "run-1", "status": "started"}),
            (200, {"run_id": "run-1", "status": "running"}),
            (200, {"run_id": "run-1", "status": "completed", "output": "done"}),
        ])

        def fake_request(method, url, *, json_body=None, headers=None, timeout=0, **kwargs):
            calls.append((method, url, json_body, headers or {}))
            return next(responses)

        with patch("hierarchy.hermes_runtime.request", side_effect=fake_request), patch("hierarchy.hermes_runtime.time.sleep"):
            self.assertEqual(self.client.run_turn(self.bot, "You are Owl.", "Do work"), "done")

        run_body = calls[1][2] or {}
        self.assertEqual(run_body["session_id"], "bot-chat")
        self.assertEqual(run_body["provider"], "openai-codex")
        self.assertEqual(run_body["model"], "gpt-5.4")
        self.assertIn(f"/p/{profile}/v1/runs", calls[1][1])
        self.assertEqual(calls[1][3]["Authorization"], "Bearer secret-key")

    def test_provider_mapping_covers_both_subscription_oauth_backends(self) -> None:
        self.assertEqual(HermesRuntime.provider_for("chatgpt"), "openai-codex")
        self.assertEqual(HermesRuntime.provider_for("grok"), "xai-oauth")
        self.assertEqual(HermesRuntime.provider_for("openai"), "openai-api")

    def test_api_key_is_scoped_to_selected_profile_provider(self) -> None:
        hierarchy_home = self.root / "hierarchy"
        hierarchy_home.mkdir()
        (hierarchy_home / "auth.json").write_text(json.dumps({
            "keys": {
                "openai": {"api_key": "openai-secret"},
                "xai": {"api_key": "xai-secret"},
            }
        }))
        profile = self.client._profile_name(self.bot)
        profile_dir = self.client._profile_dir(profile)
        profile_dir.mkdir(parents=True)
        state = HermesBotState(profile, "session-1", "profile-key")
        openai_bot = Bot(self.bot.id, "Owl", "Chief", "Coordinates", provider="openai")
        self.client._sync_profile(openai_bot, "You are Owl.", state)
        profile_env = (profile_dir / ".env").read_text()
        self.assertIn("OPENAI_API_KEY=openai-secret", profile_env)
        self.assertNotIn("XAI_API_KEY", profile_env)

    def test_oauth_import_is_passed_on_stdin_not_command_line(self) -> None:
        completed = unittest.mock.Mock(returncode=0, stdout='{"ok": true}', stderr="")
        tokens = {"access_token": "access-secret", "refresh_token": "refresh-secret"}
        with patch("hierarchy.hermes_runtime.subprocess.run", return_value=completed) as run:
            self.client.import_oauth("chatgpt", tokens)
        command = run.call_args.args[0]
        self.assertNotIn("access-secret", " ".join(command))
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["provider"], "openai-codex")
        self.assertEqual(payload["tokens"], tokens)


if __name__ == "__main__":
    unittest.main()
