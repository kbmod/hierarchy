"""Computer tools the bots drive: shell, files, HTTP, and DMs."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_OUTPUT = 8000
MAX_FETCH = 200_000


def parse_tool(text: str) -> dict[str, Any] | None:
    """Return the last JSON object in ``text`` that has a ``tool`` key."""
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            i = start + 1
            continue
        if isinstance(obj, dict) and obj.get("tool"):
            found = obj
        i = start + max(end, 1)
    return found


def workspace(home: Path) -> Path:
    path = Path(home) / "computer"
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(
            "This is the shared agent computer. Bots work here.\n"
            "Per-bot scratch lives in bots/<id>/work.\n",
            encoding="utf-8",
        )
    return path


def bot_work(home: Path, bot_id: str) -> Path:
    path = Path(home) / "bots" / bot_id / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(home: Path, raw: str, *, bot_id: str | None = None) -> Path:
    text = (raw or "").strip() or "."
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = workspace(home) / path
    return path.resolve()


def shell(cmd: str, cwd: Path, timeout: int = 90) -> str:
    cmd = cmd.strip()
    if not cmd:
        return "(empty command)"
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "HIERARCHY_WORKSPACE": str(cwd)},
        )
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s) {cmd}"
    except OSError as exc:
        return f"(failed) {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not out:
        out = f"(exit {proc.returncode})"
    return out[-MAX_OUTPUT:]


def read_file(path: Path) -> str:
    if not path.exists():
        return f"(missing) {path}"
    if path.is_dir():
        return list_dir(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"(unreadable) {exc}"
    if b"\x00" in data[:1024]:
        return f"(binary {len(data)} bytes) {path}"
    return data.decode("utf-8", errors="replace")[-MAX_OUTPUT:]


def write_file(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path} ({len(content)} chars)"


def list_dir(path: Path) -> str:
    if not path.exists():
        return f"(missing) {path}"
    if path.is_file():
        return str(path)
    rows: list[str] = []
    try:
        children = sorted(path.iterdir())
    except OSError as exc:
        return f"(unreadable) {exc}"
    for child in children[:200]:
        mark = "/" if child.is_dir() else ""
        rows.append(f"{child.name}{mark}")
    extra = len(children) - 200
    if extra > 0:
        rows.append(f"… {extra} more")
    return "\n".join(rows) or "(empty)"


def http_fetch(url: str, timeout: int = 30) -> str:
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return "(only http/https URLs)"
    req = Request(url, headers={"User-Agent": "HierarchyBot/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_FETCH + 1)
            status = getattr(resp, "status", 200)
    except HTTPError as exc:
        return f"(http {exc.code}) {exc.reason}"
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        return f"(fetch failed) {exc}"
    text = body[:MAX_FETCH].decode("utf-8", errors="replace")
    if len(body) > MAX_FETCH:
        text += "\n…(truncated)"
    return f"HTTP {status}\n{text}"


def run_tool(home: Path, bot_id: str, call: dict[str, Any], *, dm=None) -> str:
    name = str(call.get("tool") or "").strip().lower()
    cwd = workspace(home)
    if name in {"done", "reply"}:
        return str(call.get("reply") or call.get("text") or "")
    if name in {"shell", "exec", "bash"}:
        return shell(str(call.get("cmd") or call.get("command") or ""), cwd)
    if name in {"read", "read_file"}:
        return read_file(resolve_path(home, str(call.get("path") or "")))
    if name in {"write", "write_file"}:
        return write_file(
            resolve_path(home, str(call.get("path") or "")),
            str(call.get("content") or call.get("text") or ""),
        )
    if name in {"list", "ls", "list_dir"}:
        return list_dir(resolve_path(home, str(call.get("path") or ".")))
    if name in {"fetch", "http", "browse"}:
        return http_fetch(str(call.get("url") or ""))
    if name in {"message", "dm", "message_bot"}:
        if dm is None:
            return "(dm unavailable)"
        to = str(call.get("to") or call.get("name") or "")
        text = str(call.get("text") or call.get("content") or "")
        return dm(to, text)
    return f"(unknown tool {name})"
