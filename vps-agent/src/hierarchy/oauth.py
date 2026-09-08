"""Device-code OAuth for Grok (RFC 8628) and ChatGPT/Codex (OpenAI's custom flow).

Public client IDs are the ones Grok CLI and Codex CLI use. They are not secrets.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable

from hierarchy import auth
from hierarchy.http import HttpError, request

XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_DEVICE_URL = "https://auth.x.ai/oauth2/device/code"
XAI_TOKEN_URL = "https://auth.x.ai/oauth2/token"
XAI_SCOPE = "openid profile email offline_access grok-cli:access api:access"
XAI_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

CHATGPT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CHATGPT_DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
CHATGPT_DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
CHATGPT_TOKEN_URL = "https://auth.openai.com/oauth/token"
CHATGPT_DEVICE_REDIRECT = "https://auth.openai.com/deviceauth/callback"
CHATGPT_VERIFY_URL = "https://auth.openai.com/codex/device"
CHATGPT_HEADERS = {
    "originator": "codex_cli_rs",
    "User-Agent": "Hierarchy/1.0",
}


@dataclass
class DevicePending:
    provider: str
    user_code: str
    verification_uri: str
    interval: float
    expires_at: float
    extra: dict[str, Any]


HttpFn = Callable[..., tuple[int, Any]]


def start_grok(*, http: HttpFn = request) -> DevicePending:
    _, body = http(
        "POST",
        XAI_DEVICE_URL,
        form={
            "client_id": XAI_CLIENT_ID,
            "scope": XAI_SCOPE,
        },
        timeout=30,
    )
    if not isinstance(body, dict) or not body.get("device_code"):
        raise RuntimeError(f"grok device-code start failed: {body!r}")
    interval = float(body.get("interval") or 5)
    expires = float(body.get("expires_in") or 300)
    uri = str(body.get("verification_uri_complete") or body.get("verification_uri") or "")
    return DevicePending(
        provider="grok",
        user_code=str(body.get("user_code") or ""),
        verification_uri=uri,
        interval=max(1.0, interval),
        expires_at=time.time() + expires,
        extra={"device_code": str(body["device_code"])},
    )


def poll_grok(pending: DevicePending, *, http: HttpFn = request) -> dict[str, Any] | None:
    try:
        _, body = http(
            "POST",
            XAI_TOKEN_URL,
            form={
                "grant_type": XAI_DEVICE_GRANT,
                "device_code": str(pending.extra["device_code"]),
                "client_id": XAI_CLIENT_ID,
            },
            timeout=30,
        )
    except HttpError as exc:
        err = _error_code(exc.body)
        if err in {"authorization_pending", "slow_down"} or exc.status in {400, 403, 404}:
            if err == "slow_down":
                pending.interval += 5
            if err in {"access_denied", "expired_token"}:
                raise RuntimeError(f"grok oauth {err}") from exc
            return None
        raise
    if not isinstance(body, dict) or not body.get("access_token"):
        return None
    return _token_row(body)


def start_chatgpt(*, http: HttpFn = request) -> DevicePending:
    _, body = http(
        "POST",
        CHATGPT_DEVICE_CODE_URL,
        json_body={"client_id": CHATGPT_CLIENT_ID},
        headers=CHATGPT_HEADERS,
        timeout=30,
    )
    if not isinstance(body, dict):
        raise RuntimeError(f"chatgpt device-code start failed: {body!r}")
    device_id = str(body.get("device_auth_id") or body.get("deviceAuthId") or "")
    user_code = str(body.get("user_code") or body.get("userCode") or "")
    interval = float(body.get("interval") or body.get("intervalSeconds") or 5)
    expires = float(body.get("expires_in") or 900)
    uri = str(body.get("verification_uri") or body.get("verificationUri") or CHATGPT_VERIFY_URL)
    if not device_id or not user_code:
        raise RuntimeError(f"chatgpt device-code start failed: {body!r}")
    return DevicePending(
        provider="chatgpt",
        user_code=user_code,
        verification_uri=uri,
        interval=max(1.0, interval),
        expires_at=time.time() + expires,
        extra={"device_auth_id": device_id},
    )


def poll_chatgpt(pending: DevicePending, *, http: HttpFn = request) -> dict[str, Any] | None:
    try:
        _, body = http(
            "POST",
            CHATGPT_DEVICE_TOKEN_URL,
            json_body={
                "device_auth_id": pending.extra["device_auth_id"],
                "user_code": pending.user_code,
            },
            headers=CHATGPT_HEADERS,
            timeout=30,
        )
    except HttpError as exc:
        if exc.status in {403, 404}:
            return None
        raise
    if not isinstance(body, dict):
        return None
    code = str(body.get("authorization_code") or body.get("authorizationCode") or "")
    verifier = str(body.get("code_verifier") or body.get("codeVerifier") or "")
    if not code:
        return None
    return _exchange_chatgpt(code, verifier, http=http)


def _exchange_chatgpt(code: str, verifier: str, *, http: HttpFn) -> dict[str, Any]:
    if not verifier:
        verifier = secrets.token_urlsafe(64)
    _, body = http(
        "POST",
        CHATGPT_TOKEN_URL,
        form={
            "grant_type": "authorization_code",
            "client_id": CHATGPT_CLIENT_ID,
            "code": code,
            "redirect_uri": CHATGPT_DEVICE_REDIRECT,
            "code_verifier": verifier,
        },
        headers=CHATGPT_HEADERS,
        timeout=30,
    )
    if not isinstance(body, dict) or not body.get("access_token"):
        raise RuntimeError(f"chatgpt token exchange failed: {body!r}")
    return _token_row(body)


def refresh_oauth(home: str, provider: str, *, http: HttpFn = request) -> dict[str, Any] | None:
    data = auth.load(home)
    row = (data.get("oauth") or {}).get(provider)
    if not isinstance(row, dict) or not row.get("refresh_token"):
        return None
    if provider == "grok":
        _, body = http(
            "POST",
            XAI_TOKEN_URL,
            form={
                "grant_type": "refresh_token",
                "refresh_token": str(row["refresh_token"]),
                "client_id": XAI_CLIENT_ID,
            },
            timeout=30,
        )
    elif provider == "chatgpt":
        _, body = http(
            "POST",
            CHATGPT_TOKEN_URL,
            form={
                "grant_type": "refresh_token",
                "refresh_token": str(row["refresh_token"]),
                "client_id": CHATGPT_CLIENT_ID,
            },
            headers=CHATGPT_HEADERS,
            timeout=30,
        )
    else:
        return None
    if not isinstance(body, dict) or not body.get("access_token"):
        return None
    tokens = _token_row(body)
    if not tokens.get("refresh_token"):
        tokens["refresh_token"] = row["refresh_token"]
    auth.set_oauth(home, provider, tokens)
    return tokens


def wait(pending: DevicePending, *, http: HttpFn = request, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    poller = poll_grok if pending.provider == "grok" else poll_chatgpt
    while time.time() < pending.expires_at:
        tokens = poller(pending, http=http)
        if tokens:
            return tokens
        sleep(pending.interval)
    raise TimeoutError(f"{pending.provider} oauth timed out")


def login(home: str, provider: str, *, http: HttpFn = request, printer: Callable[[str], None] = print) -> dict[str, Any]:
    if provider == "grok":
        pending = start_grok(http=http)
    elif provider == "chatgpt":
        pending = start_chatgpt(http=http)
    else:
        raise ValueError(f"unknown oauth provider {provider!r}")
    printer(f"Open {pending.verification_uri}")
    printer(f"Code: {pending.user_code}")
    printer("Waiting for approval…")
    tokens = wait(pending, http=http)
    return auth.set_oauth(home, provider, tokens)


def _token_row(body: dict[str, Any]) -> dict[str, Any]:
    expires_in = float(body.get("expires_in") or 3600)
    return {
        "access_token": str(body.get("access_token") or ""),
        "refresh_token": str(body.get("refresh_token") or ""),
        "expires_at": time.time() + expires_in,
        "token_type": str(body.get("token_type") or "Bearer"),
    }


def _error_code(body: str) -> str:
    try:
        import json

        data = json.loads(body)
        if isinstance(data, dict):
            return str(data.get("error") or "")
    except ValueError:
        return ""
    return ""
