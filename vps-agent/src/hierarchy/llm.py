"""Model calls. API keys use OpenAI-compatible chat/completions. Grok OAuth does too.

ChatGPT OAuth tokens are for Codex (``chatgpt.com/backend-api/codex``), not api.openai.com.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any, Callable

from hierarchy import auth, oauth
from hierarchy.http import HttpError, request
from hierarchy.models import Bot

CompleteFn = Callable[[Bot, str, list[dict[str, str]], str], str]


def stub_complete(bot: Bot, instructions: str, history: list[dict[str, str]], text: str) -> str:
    snippet = " ".join(text.split())
    if len(snippet) > 160:
        snippet = snippet[:157] + "..."
    return f"{bot.name} ({bot.job}): {snippet}"


def complete(home: str, bot: Bot, instructions: str, history: list[dict[str, str]], text: str) -> str:
    wanted = (bot.provider or "").strip() or None
    if wanted == "stub":
        return stub_complete(bot, instructions, history, text)
    cred = auth.credential(home, provider=wanted)
    if cred is None:
        if wanted:
            return (
                f"{bot.name}: provider {wanted!r} is not connected. "
                "Add it in Settings → Providers, or pick another provider on this bot."
            )
        return stub_complete(bot, instructions, history, text)
    messages = _messages(bot, instructions, history, text)
    model = (bot.model or "").strip() or str(cred.get("model") or "")
    if cred.get("kind") == "oauth" and cred.get("provider") == "chatgpt":
        token = _fresh_access(home, cred)
        return chatgpt_complete(token, model or "gpt-5.4", messages)
    if cred.get("kind") == "oauth" and cred.get("provider") == "grok":
        token = _fresh_access(home, cred)
        return chat_completions(
            str(cred.get("base_url") or "https://api.x.ai/v1"),
            token,
            model or "grok-4.5",
            messages,
        )
    return chat_completions(
        str(cred.get("base_url") or ""),
        str(cred.get("api_key") or ""),
        model,
        messages,
    )


def chat_completions(base_url: str, api_key: str, model: str, messages: list[dict[str, str]], *, http=request) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    _, body = http(
        "POST",
        url,
        json_body={"model": model, "messages": messages, "max_tokens": 1600, "temperature": 0.6},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    if not isinstance(body, dict):
        raise RuntimeError(f"bad completions response: {body!r}")
    choices = body.get("choices") or []
    if choices:
        content = choices[0].get("message", {}).get("content")
        if content:
            return str(content)
    raise RuntimeError(f"empty completions response: {body!r}")


def chatgpt_complete(access_token: str, model: str, messages: list[dict[str, str]], *, http=request) -> str:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    account = _chatgpt_account_id(access_token)
    if account:
        headers["ChatGPT-Account-Id"] = account
    payload = {
        "model": model,
        "instructions": next((m["content"] for m in messages if m["role"] == "system"), ""),
        "input": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ],
        "stream": False,
    }
    try:
        _, body = http(
            "POST",
            "https://chatgpt.com/backend-api/codex/responses",
            json_body=payload,
            headers=headers,
            timeout=120,
        )
    except HttpError as exc:
        raise RuntimeError(f"chatgpt oauth request failed: {exc}") from exc
    text = _codex_text(body)
    if not text:
        raise RuntimeError(f"empty chatgpt oauth response: {body!r}")
    return text


def _fresh_access(home: str, cred: dict[str, Any]) -> str:
    expires = float(cred.get("expires_at") or 0)
    token = str(cred.get("access_token") or "")
    if token and expires > time.time() + 60:
        return token
    provider = str(cred.get("provider") or "")
    refreshed = oauth.refresh_oauth(home, provider)
    if refreshed and refreshed.get("access_token"):
        return str(refreshed["access_token"])
    if token:
        return token
    raise RuntimeError(f"{provider} oauth has no access token — run: python -m hierarchy login {provider}")


def _messages(bot: Bot, instructions: str, history: list[dict[str, str]], text: str) -> list[dict[str, str]]:
    system = instructions.strip() or f"You are {bot.name}, {bot.job}. {bot.description}"
    out = [{"role": "system", "content": system}]
    for row in history:
        role = row.get("role") or "user"
        if role not in {"user", "assistant"}:
            continue
        content = (row.get("content") or "").strip()
        if content:
            out.append({"role": role, "content": content})
    if not out or out[-1].get("content") != text:
        out.append({"role": "user", "content": text})
    return out


def _chatgpt_account_id(access_token: str) -> str:
    parts = access_token.split(".")
    if len(parts) < 2:
        return ""
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return ""
    claims = data.get("https://api.openai.com/auth")
    if isinstance(claims, dict):
        return str(claims.get("chatgpt_account_id") or claims.get("account_id") or "")
    return ""


def _codex_text(body: Any) -> str:
    if isinstance(body, str) and body.strip():
        return body.strip()
    if not isinstance(body, dict):
        return ""
    if body.get("output_text"):
        return str(body["output_text"])
    chunks: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("text"):
                chunks.append(str(part["text"]))
    if chunks:
        return "".join(chunks)
    choices = body.get("choices") or []
    if choices:
        return str(choices[0].get("message", {}).get("content") or "")
    return ""
