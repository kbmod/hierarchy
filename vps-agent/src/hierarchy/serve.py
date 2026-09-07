"""Local HTTP API + a single-page roster UI. Stdlib only."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hierarchy import auth, computer, oauth, projects, tools
from hierarchy.jobs import JobBoard
from hierarchy.runtime import Runtime
from hierarchy.seed import ensure_floor

DEFAULT_PORT = 8765


def default_home() -> Path:
    override = os.environ.get("HIERARCHY_HOME")
    if override:
        return Path(override)
    return Path.home() / ".hierarchy"


def _token() -> str:
    return (os.environ.get("HIERARCHY_TOKEN") or "").strip()


class Server:
    def __init__(self, runtime: Runtime, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        self.runtime = runtime
        self.pending_oauth: dict[str, oauth.DevicePending] = {}
        self.jobs = JobBoard()
        self._stop = threading.Event()
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(self))
        self._ticker = threading.Thread(target=self._routines_loop, daemon=True)
        self._ticker.start()

    def _routines_loop(self) -> None:
        while not self._stop.wait(45):
            try:
                _tick_routines(self)
            except Exception:
                continue

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        self._stop.set()
        self._httpd.shutdown()
        self._httpd.server_close()


def _make_handler(server: Server) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _authorized(self) -> bool:
            expected = _token()
            if not expected:
                return True
            header = self.headers.get("Authorization") or ""
            if header == f"Bearer {expected}":
                return True
            if (self.headers.get("X-Hierarchy-Token") or "") == expected:
                return True
            return False

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Hierarchy-Token")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            rt = server.runtime
            if path in {"/", "/index.html"}:
                self._html(_PAGE)
                return
            if path == "/api/health":
                self._json(
                    200,
                    {
                        "ok": True,
                        "auth": bool(_token()),
                        "bots": len(rt.store.list_bots()),
                        "computer": True,
                        "jobs": True,
                    },
                )
                return
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            if path == "/api/auth":
                self._json(200, auth.public_status(home=rt.home))
                return
            if path == "/api/bots":
                self._json(200, {"bots": rt.roster()})
                return
            if path == "/api/computer":
                self._json(200, computer.read_shell(Path(rt.home)))
                return
            if path == "/api/projects":
                self._json(200, {"projects": projects.list_projects(Path(rt.home))})
                return
            if path == "/api/jobs":
                bot_id = (parse_qs(urlparse(self.path).query).get("bot") or [None])[0]
                self._json(200, {"jobs": server.jobs.list(bot_id)})
                return
            if path.startswith("/api/jobs/"):
                row = server.jobs.get(path.split("/")[3])
                if row is None:
                    self._json(404, {"error": "unknown job"})
                    return
                self._json(200, row)
                return
            if path == "/api/computer/files":
                rel = (parse_qs(urlparse(self.path).query).get("path") or ["."])[0]
                target = tools.resolve_path(Path(rt.home), rel)
                self._json(
                    200,
                    {
                        "path": str(target),
                        "listing": tools.list_dir(target),
                    },
                )
                return
            if path.startswith("/api/bots/") and path.endswith("/history"):
                bot_id = path.split("/")[3]
                try:
                    self._json(200, {"history": rt.history(bot_id)})
                except KeyError:
                    self._json(404, {"error": "unknown bot"})
                return
            if path.startswith("/api/bots/") and path.endswith("/computer"):
                bot_id = path.split("/")[3]
                try:
                    bot = rt.store.get(bot_id)
                except KeyError:
                    self._json(404, {"error": "unknown bot"})
                    return
                screen = computer.read(rt.store.bot_dir(bot.id))
                self._json(200, {"id": bot.id, "name": bot.name, **screen})
                return
            if path.startswith("/api/bots/") and path.endswith("/routines"):
                bot_id = path.split("/")[3]
                try:
                    rt.store.get(bot_id)
                except KeyError:
                    self._json(404, {"error": "unknown bot"})
                    return
                self._json(200, {"routines": _read_routines(rt, bot_id)})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            rt = server.runtime
            if path != "/api/health" and not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid json"})
                return
            try:
                if path == "/api/auth/key":
                    status = auth.set_key(
                        rt.home,
                        str(payload.get("provider") or ""),
                        str(payload.get("api_key") or ""),
                        model=str(payload["model"]) if payload.get("model") else None,
                    )
                    self._json(200, status)
                    return
                if path == "/api/auth/use":
                    self._json(200, auth.set_active(rt.home, str(payload.get("provider") or "")))
                    return
                if path == "/api/auth/oauth/start":
                    provider = str(payload.get("provider") or "")
                    pending = (
                        oauth.start_grok()
                        if provider == "grok"
                        else oauth.start_chatgpt()
                        if provider == "chatgpt"
                        else None
                    )
                    if pending is None:
                        raise ValueError("provider must be grok or chatgpt")
                    sid = uuid.uuid4().hex
                    server.pending_oauth[sid] = pending
                    self._json(
                        200,
                        {
                            "session": sid,
                            "provider": pending.provider,
                            "user_code": pending.user_code,
                            "verification_uri": pending.verification_uri,
                        },
                    )
                    return
                if path == "/api/auth/oauth/poll":
                    sid = str(payload.get("session") or "")
                    pending = server.pending_oauth.get(sid)
                    if pending is None:
                        raise ValueError("unknown oauth session")
                    tokens = (
                        oauth.poll_grok(pending) if pending.provider == "grok" else oauth.poll_chatgpt(pending)
                    )
                    if tokens is None:
                        self._json(200, {"ok": False, "pending": True})
                        return
                    server.pending_oauth.pop(sid, None)
                    self._json(200, {"ok": True, **auth.set_oauth(rt.home, pending.provider, tokens)})
                    return
                if path == "/api/floor":
                    bots = ensure_floor(rt)
                    self._json(
                        200,
                        {
                            "bots": [
                                {"id": b.id, "name": b.name, "job": b.job, "reports_to": b.reports_to}
                                for b in bots
                            ]
                        },
                    )
                    return
                if path == "/api/projects":
                    name = str(payload.get("name") or "").strip()
                    outcome = str(payload.get("outcome") or "").strip()
                    if not name or not outcome:
                        raise ValueError("name and outcome are required")
                    ensure_floor(rt)
                    lead = None
                    if payload.get("lead_id"):
                        lead = rt.store.get(str(payload["lead_id"]))
                    if lead is None:
                        lead = rt.store.find_by_name("Atlas") or rt.store.list_bots()[0]
                    specialists = [b for b in rt.store.list_bots() if b.id != lead.id]
                    row = projects.add_project(
                        Path(rt.home),
                        name=name,
                        outcome=outcome,
                        lead_id=lead.id,
                        bot_ids=[b.id for b in rt.store.list_bots()],
                    )
                    brief = (
                        f"Project: {name}\n\nOutcome:\n{outcome}\n\n"
                        "Coordinate the floor. Assign work to specialists. "
                        "Return a short plan, who owns what, and the first concrete step. "
                        "Do not take irreversible actions."
                    )
                    lead_reply = rt.chat(lead.id, brief)
                    specialist_reply = None
                    if specialists:
                        specialist_reply = rt.dm(
                            sender_id=lead.id,
                            to_id=specialists[0].id,
                            text=f"Kickoff for {name}: {outcome}. Start the first concrete step. Report back.",
                        )
                    self._json(
                        201,
                        {
                            "project": row,
                            "lead": {"bot_id": lead_reply.bot_id, "text": lead_reply.text},
                            "specialist": (
                                {"bot_id": specialist_reply.bot_id, "text": specialist_reply.text}
                                if specialist_reply
                                else None
                            ),
                        },
                    )
                    return
                if path == "/api/bots":
                    bot = rt.create(
                        str(payload.get("name") or ""),
                        str(payload.get("job") or ""),
                        str(payload.get("description") or ""),
                        reports_to=str(payload["reports_to"]) if payload.get("reports_to") else None,
                        provider=str(payload["provider"]) if "provider" in payload else None,
                        model=str(payload["model"]) if "model" in payload else None,
                    )
                    self._json(
                        201,
                        {
                            "id": bot.id,
                            "name": bot.name,
                            "job": bot.job,
                            "reports_to": bot.reports_to,
                            "provider": bot.provider,
                            "model": bot.model,
                        },
                    )
                    return
                if path.startswith("/api/bots/") and path.count("/") == 3:
                    bot_id = path.rstrip("/").split("/")[-1]
                    updated = rt.update(
                        bot_id,
                        job=str(payload["job"]) if payload.get("job") is not None else None,
                        description=str(payload["description"]) if payload.get("description") is not None else None,
                        reports_to=str(payload["reports_to"]) if payload.get("reports_to") else None,
                        clear_reports=payload.get("reports_to") == "",
                        provider=str(payload["provider"]) if "provider" in payload else None,
                        model=str(payload["model"]) if "model" in payload else None,
                    )
                    self._json(
                        200,
                        {
                            "id": updated.id,
                            "name": updated.name,
                            "job": updated.job,
                            "reports_to": updated.reports_to,
                            "provider": updated.provider,
                            "model": updated.model,
                        },
                    )
                    return
                if path.startswith("/api/bots/") and path.endswith("/chat"):
                    bot_id = path.split("/")[3]
                    text = str(payload.get("text") or "")
                    if payload.get("async"):
                        bot = rt.store.get(bot_id)
                        message = text.strip()
                        if not message:
                            raise ValueError("message is required")
                        rt.store.append(bot.id, "user", message)
                        job = server.jobs.submit(
                            bot_id=bot.id,
                            kind="chat",
                            fn=lambda bid=bot.id, msg=message: rt.complete_turn(bid, msg),
                        )
                        self._json(202, {"bot_id": bot.id, "job_id": job["id"], "status": "working", "text": ""})
                        return
                    reply = rt.chat(bot_id, text)
                    self._json(200, {"bot_id": reply.bot_id, "text": reply.text})
                    return
                if path == "/api/computer/exec":
                    cmd = str(payload.get("cmd") or payload.get("command") or "")
                    out = rt.exec_shell(cmd)
                    self._json(200, {"ok": True, "output": out, **computer.read_shell(Path(rt.home))})
                    return
                if path.startswith("/api/bots/") and path.endswith("/dm"):
                    to_id = path.split("/")[3]
                    reply = rt.dm(
                        sender_id=str(payload.get("sender_id") or ""),
                        to_id=to_id,
                        text=str(payload.get("text") or ""),
                    )
                    self._json(200, {"bot_id": reply.bot_id, "text": reply.text})
                    return
                if path.startswith("/api/bots/") and path.endswith("/routines"):
                    bot_id = path.split("/")[3]
                    rt.store.get(bot_id)
                    rows = _read_routines(rt, bot_id)
                    if payload.get("id"):
                        for row in rows:
                            if row.get("id") == payload["id"]:
                                if "active" in payload:
                                    row["active"] = bool(payload["active"])
                                if payload.get("instruction"):
                                    row["instruction"] = str(payload["instruction"])
                                if payload.get("schedule"):
                                    row["schedule"] = str(payload["schedule"])
                                break
                    else:
                        rows.append(
                            {
                                "id": uuid.uuid4().hex[:12],
                                "title": str(payload.get("title") or "Untitled routine"),
                                "schedule": str(payload.get("schedule") or "Every day at 8:00 AM"),
                                "instruction": str(payload.get("instruction") or ""),
                                "active": True,
                            }
                        )
                    _write_routines(rt, bot_id, rows)
                    self._json(200, {"routines": rows})
                    return
                if path.startswith("/api/bots/") and path.endswith("/routines/run"):
                    bot_id = path.split("/")[3]
                    rt.store.get(bot_id)
                    rid = str(payload.get("id") or "")
                    rows = _read_routines(rt, bot_id)
                    row = next((r for r in rows if r.get("id") == rid), None)
                    if row is None:
                        raise ValueError("unknown routine")
                    instruction = str(row.get("instruction") or row.get("title") or "Run the routine")
                    job = server.jobs.submit(
                        bot_id=bot_id,
                        kind="routine",
                        fn=lambda bid=bot_id, msg=instruction: rt.chat(bid, msg).text,
                    )
                    row["last_run"] = time.time()
                    _write_routines(rt, bot_id, rows)
                    self._json(202, {"job_id": job["id"], "routines": rows})
                    return
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            except KeyError:
                self._json(404, {"error": "unknown bot"})
                return
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": str(exc)})
                return
            self._json(404, {"error": "not found"})

    return Handler


def _routines_path(rt: Runtime, bot_id: str) -> Path:
    return rt.store.bot_dir(bot_id) / "routines.json"


def _read_routines(rt: Runtime, bot_id: str) -> list[dict[str, Any]]:
    path = _routines_path(rt, bot_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _write_routines(rt: Runtime, bot_id: str, rows: list[dict[str, Any]]) -> None:
    _routines_path(rt, bot_id).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _interval_seconds(schedule: str) -> float | None:
    text = (schedule or "").strip().lower()
    match = re.search(r"every\s+(\d+)\s*(second|sec|s|minute|min|m|hour|hr|h)s?", text)
    if not match:
        return None
    n = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("s"):
        return float(n)
    if unit.startswith("h"):
        return float(n * 3600)
    return float(n * 60)


def _tick_routines(server: Server) -> None:
    rt = server.runtime
    now = time.time()
    for bot in rt.store.list_bots():
        rows = _read_routines(rt, bot.id)
        changed = False
        for row in rows:
            if not row.get("active"):
                continue
            interval = _interval_seconds(str(row.get("schedule") or ""))
            if interval is None or interval < 30:
                continue
            last = float(row.get("last_run") or 0)
            if now - last < interval:
                continue
            instruction = str(row.get("instruction") or row.get("title") or "Run the routine")
            server.jobs.submit(
                bot_id=bot.id,
                kind="routine",
                fn=lambda bid=bot.id, msg=instruction: rt.chat(bid, msg).text,
            )
            row["last_run"] = now
            changed = True
        if changed:
            _write_routines(rt, bot.id, rows)


_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>hierarchy</title>
<style>
  :root { color-scheme: dark; }
  body { font: 15px/1.4 system-ui, sans-serif; margin: 0; color: #e8eaed; background: #111; }
  main { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
  aside { border-right: 1px solid #333; padding: 16px; }
  section { padding: 16px; display: flex; flex-direction: column; }
  h1 { font-size: 16px; margin: 0 0 12px; }
  button, input, textarea, select { font: inherit; color: inherit; background: #1c1c1c; border: 1px solid #444; border-radius: 6px; padding: 8px; }
  button { cursor: pointer; }
  .bot { display: block; width: 100%; text-align: left; margin: 0 0 8px; }
  .bot.active { border-color: #888; }
  #log { flex: 1; white-space: pre-wrap; overflow: auto; border: 1px solid #333; padding: 12px; min-height: 240px; }
  form { display: flex; gap: 8px; margin-top: 12px; }
  form textarea { flex: 1; min-height: 48px; }
  .muted { color: #9aa0a6; font-size: 13px; }
</style>
<main>
  <aside>
    <h1>Bots</h1>
    <div id="roster"></div>
    <p class="muted">Model</p>
    <div id="auth-status" class="muted"></div>
    <select id="provider" style="width:100%;margin-top:8px">
      <option value="stub">stub (offline)</option>
      <option value="xai">xAI API key</option>
      <option value="openai">OpenAI API key</option>
      <option value="openrouter">OpenRouter API key</option>
      <option value="grok">Grok OAuth</option>
      <option value="chatgpt">ChatGPT OAuth</option>
    </select>
    <input id="apikey" type="password" placeholder="API key" style="margin-top:8px;width:100%">
    <button id="save-key" style="margin-top:8px;width:100%">Save key</button>
    <button id="oauth" style="margin-top:8px;width:100%">OAuth device login</button>
    <p id="oauth-hint" class="muted"></p>
    <p class="muted">New bot</p>
    <input id="name" placeholder="name">
    <input id="job" placeholder="job" style="margin-top:8px">
    <textarea id="desc" placeholder="description" style="margin-top:8px"></textarea>
    <button id="create" style="margin-top:8px;width:100%">Create</button>
  </aside>
  <section>
    <h1 id="title">Select a bot</h1>
    <div id="log"></div>
    <form id="composer">
      <textarea id="text" placeholder="Message"></textarea>
      <button>Send</button>
    </form>
  </section>
</main>
<script>
let current = null;
async function j(url, opts){ const r = await fetch(url, opts); return r.json(); }
async function loadRoster(){
  const data = await j('/api/bots');
  const box = document.getElementById('roster');
  box.innerHTML = '';
  for (const bot of data.bots){
    const b = document.createElement('button');
    b.className = 'bot' + (current === bot.id ? ' active' : '');
    b.textContent = bot.name + ' — ' + bot.job;
    b.onclick = () => openBot(bot);
    box.appendChild(b);
  }
}
async function openBot(bot){
  current = bot.id;
  document.getElementById('title').textContent = bot.name + ' · ' + bot.job;
  const data = await j('/api/bots/' + bot.id + '/history');
  document.getElementById('log').textContent = data.history.map(m => m.role + ': ' + m.content).join('\\n\\n');
  await loadRoster();
}
document.getElementById('create').onclick = async () => {
  await j('/api/bots', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    name: document.getElementById('name').value,
    job: document.getElementById('job').value,
    description: document.getElementById('desc').value,
  })});
  document.getElementById('name').value = '';
  document.getElementById('job').value = '';
  document.getElementById('desc').value = '';
  await loadRoster();
};
document.getElementById('composer').onsubmit = async (e) => {
  e.preventDefault();
  if (!current) return;
  const text = document.getElementById('text').value;
  document.getElementById('text').value = '';
  await j('/api/bots/' + current + '/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
  const bot = (await j('/api/bots')).bots.find(b => b.id === current);
  if (bot) await openBot(bot);
};
loadRoster();
loadAuth();
async function loadAuth(){
  const s = await j('/api/auth');
  document.getElementById('auth-status').textContent = 'active: ' + s.active;
  document.getElementById('provider').value = s.active || 'stub';
}
document.getElementById('save-key').onclick = async () => {
  const provider = document.getElementById('provider').value;
  if (provider === 'stub' || provider === 'grok' || provider === 'chatgpt') {
    await j('/api/auth/use', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({provider})});
  } else {
    await j('/api/auth/key', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
      provider, api_key: document.getElementById('apikey').value
    })});
    document.getElementById('apikey').value = '';
  }
  await loadAuth();
};
document.getElementById('oauth').onclick = async () => {
  const provider = document.getElementById('provider').value;
  if (provider !== 'grok' && provider !== 'chatgpt') {
    document.getElementById('oauth-hint').textContent = 'Pick Grok OAuth or ChatGPT OAuth first.';
    return;
  }
  const start = await j('/api/auth/oauth/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({provider})});
  document.getElementById('oauth-hint').textContent = 'Open ' + start.verification_uri + '  code ' + start.user_code;
  const tick = async () => {
    const p = await j('/api/auth/oauth/poll', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session: start.session})});
    if (p.ok) { document.getElementById('oauth-hint').textContent = 'Signed in.'; await loadAuth(); return; }
    setTimeout(tick, 3000);
  };
  setTimeout(tick, 3000);
};
</script>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hierarchy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--store", default=str(default_home()))
    args = parser.parse_args(argv)
    runtime = Runtime(args.store)
    server = Server(runtime, host=args.host, port=args.port)
    print(f"hierarchy {server.url}  store={args.store}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
