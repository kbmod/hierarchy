from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hierarchy import auth, llm, oauth
from hierarchy.http import HttpError
from hierarchy.models import Bot
from hierarchy.runtime import Runtime


class AuthStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_api_key_is_stored_but_not_in_public_status(self) -> None:
        status = auth.set_key(self.home, "xai", "xai-secret-key", model="grok-4.6")
        self.assertEqual(status["active"], "xai")
        self.assertTrue(status["keys"]["xai"]["configured"])
        dumped = Path(self.home).joinpath("auth.json").read_text(encoding="utf-8")
        self.assertIn("xai-secret-key", dumped)
        self.assertNotIn("xai-secret-key", str(status))

    def test_runtime_uses_stub_without_credentials(self) -> None:
        rt = Runtime(self.home)
        bot = rt.create("owl", "Chief of staff", "Routes work")
        reply = rt.chat(bot.id, "hello")
        self.assertIn("owl", reply.text)

    def test_per_bot_provider_and_model(self) -> None:
        auth.set_key(self.home, "xai", "xai-secret-key", model="grok-4.5")
        auth.set_key(self.home, "openai", "openai-secret", model="gpt-4.1")
        auth.set_active(self.home, "xai")
        rt = Runtime(self.home)
        grok_bot = rt.create("g", "Grok bot", "Uses grok", provider="xai", model="grok-4.6")
        oai_bot = rt.create("o", "OpenAI bot", "Uses openai", provider="openai", model="gpt-4o")
        stub_bot = rt.create("s", "Stub bot", "Offline", provider="stub")
        self.assertEqual(rt.store.get(grok_bot.id).provider, "xai")
        self.assertEqual(rt.store.get(grok_bot.id).model, "grok-4.6")
        self.assertEqual(auth.credential(self.home, "openai")["provider"], "openai")
        self.assertEqual(auth.credential(self.home)["provider"], "xai")
        reply = rt.chat(stub_bot.id, "ping")
        self.assertIn("s", reply.text)
        missing = rt.create("m", "Missing", "No chatgpt", provider="chatgpt")
        miss = rt.chat(missing.id, "hi")
        self.assertIn("chatgpt", miss.text)
        updated = rt.update(oai_bot.id, provider="xai", model="grok-4.5")
        self.assertEqual(updated.provider, "xai")
        self.assertEqual(updated.model, "grok-4.5")


class CompletionsTests(unittest.TestCase):
    def test_chat_completions_reads_choice_text(self) -> None:
        def http(method, url, **kwargs):
            self.assertIn("/chat/completions", url)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer k")
            return 200, {"choices": [{"message": {"content": "pong"}}]}

        text = llm.chat_completions("https://api.x.ai/v1", "k", "grok-4.6", [{"role": "user", "content": "ping"}], http=http)
        self.assertEqual(text, "pong")


class GrokOauthTests(unittest.TestCase):
    def test_device_start_and_poll(self) -> None:
        calls = []

        def http(method, url, **kwargs):
            calls.append(url)
            if url.endswith("/device/code"):
                return 200, {
                    "device_code": "dev-1",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://auth.x.ai/device",
                    "interval": 1,
                    "expires_in": 60,
                }
            if url.endswith("/token"):
                form = kwargs.get("form") or {}
                if form.get("device_code") == "dev-1":
                    return 200, {"access_token": "atk", "refresh_token": "rtk", "expires_in": 120}
            raise AssertionError(url)

        pending = oauth.start_grok(http=http)
        self.assertEqual(pending.user_code, "ABCD-1234")
        tokens = oauth.poll_grok(pending, http=http)
        assert tokens is not None
        self.assertEqual(tokens["access_token"], "atk")
        self.assertEqual(tokens["refresh_token"], "rtk")

    def test_poll_pending_returns_none(self) -> None:
        pending = oauth.DevicePending(
            provider="grok",
            user_code="X",
            verification_uri="https://example",
            interval=1,
            expires_at=0,
            extra={"device_code": "dev-1"},
        )

        def http(method, url, **kwargs):
            raise HttpError(400, '{"error":"authorization_pending"}', url)

        self.assertIsNone(oauth.poll_grok(pending, http=http))


class ChatgptOauthTests(unittest.TestCase):
    def test_device_then_token_exchange(self) -> None:
        def http(method, url, **kwargs):
            if url.endswith("/deviceauth/usercode"):
                return 200, {"deviceAuthId": "id-1", "userCode": "WXYZ", "intervalSeconds": 1, "expires_in": 60}
            if url.endswith("/deviceauth/token"):
                return 200, {"authorizationCode": "acode", "codeVerifier": "verif"}
            if url.endswith("/oauth/token"):
                form = kwargs.get("form") or {}
                self.assertEqual(form.get("code"), "acode")
                self.assertEqual(form.get("code_verifier"), "verif")
                return 200, {"access_token": "chat-atk", "refresh_token": "chat-rtk", "expires_in": 60}
            raise AssertionError(url)

        pending = oauth.start_chatgpt(http=http)
        self.assertEqual(pending.user_code, "WXYZ")
        tokens = oauth.poll_chatgpt(pending, http=http)
        assert tokens is not None
        self.assertEqual(tokens["access_token"], "chat-atk")


class LlmMessagesTests(unittest.TestCase):
    def test_system_prompt_from_instructions(self) -> None:
        bot = Bot(id="1", name="lead", job="Lead", description="x")
        msgs = llm._messages(bot, "Stay in role.", [{"role": "user", "content": "hi"}], "hi")
        self.assertEqual(msgs[0], {"role": "system", "content": "Stay in role."})
        self.assertEqual(msgs[-1]["content"], "hi")
        self.assertEqual(sum(1 for m in msgs if m["content"] == "hi"), 1)


if __name__ == "__main__":
    unittest.main()
