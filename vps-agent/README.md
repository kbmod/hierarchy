# hierarchy

A small multi-bot runtime. Roster, isolated stores, in-process chat and DMs.

Each bot has its own directory. One process owns every bot. A DM is written to the target inbox and drained immediately.

The Hierarchy Android app talks to this agent on your VPS. The VPS is the bots' computer: shell, files, HTTP, and background jobs.

## Run on a VPS

Do not leave a terminal open. Install it as a systemd service:

```bash
cd vps-agent
sudo bash scripts/install-service.sh
```

That prints a URL (`http://YOUR_VPS_IP:8765`) and a token, enables the service, and restarts it on reboot. Then paste those into the phone app. Open TCP 8765 on the firewall / security group.

The installer runs `hierarchy.service` as a non-root service user. With `sudo`,
that defaults to `SUDO_USER`; choose another account explicitly with
`HIERARCHY_SERVICE_USER=...`. The selected account owns `/var/lib/hierarchy`,
and the unit sets its resolved home directory and primary group. An unresolved
or explicit root service user is rejected.

If that account has Codex installed, the installer records its executable as
`HIERARCHY_CODEX_BIN` and uses `$HOME/.codex` as `HIERARCHY_CODEX_HOME` (both can
be overridden before installation). If the Codex home does not exist yet, the
installer creates it with service-user ownership so a later login works without
another ownership migration. The installer checks paths only; it never reads or
copies Codex credentials. `HIERARCHY_CHATGPT_BACKEND=auto` remains the default
so non-Codex installs and Grok continue to work unchanged.
On upgrades, the installer preserves an existing service user, backend, and
Codex bin/home unless the corresponding `HIERARCHY_*` variable is explicitly
set for that run.

For ChatGPT subscription access through Codex app-server, authenticate as the
same Unix user that runs the service, for example:

```bash
sudo -u <service-user> -H codex login
```

If the service user is the account that owns your existing Codex installation,
its existing `~/.codex/auth.json` is the credential owner. Otherwise, log in as
the service user with the Codex device flow. Do not copy that file into
`~/.hierarchy` or `/var/lib/hierarchy`: Codex owns refresh-token rotation, and
duplicating a single-use refresh token can invalidate the other client.

The current Hierarchy HTTP provider and the Codex app-server runtime are
separate paths. With `HIERARCHY_CHATGPT_BACKEND=auto` (the installer default),
ChatGPT bots use Codex when the configured Codex executable and home are
available. Set `HIERARCHY_CHATGPT_BACKEND=http` to use Hierarchy's own ChatGPT
OAuth flow instead; do not keep both credential paths active accidentally.

Codex app-server runs unattended as the service user. Each bot is given its
isolated working directory under `/var/lib/hierarchy/bots/<bot-id>/work`; the
Codex process may use the network, but Hierarchy declines command, file-change,
permission, and escalation approval requests. A turn can therefore explain a
command without executing it when Codex requests approval. Treat subscription
access and bot workspaces as trusted operator resources, and use the separate
Hierarchy shell only for explicitly authorized maintenance.

```bash
systemctl status hierarchy
journalctl -u hierarchy -f
```

Foreground (debug only):

```bash
export HIERARCHY_TOKEN="$(openssl rand -hex 24)"
export HIERARCHY_HOME="$HOME/.hierarchy"
PYTHONPATH=src python3 -m hierarchy serve --host 0.0.0.0 --port 8765
```

```bash
# API keys
python3 -m hierarchy key xai "$XAI_API_KEY"
python3 -m hierarchy key openai "$OPENAI_API_KEY"

# Hierarchy-owned OAuth device login (Grok, or ChatGPT only with HTTP backend)
python3 -m hierarchy login grok
python3 -m hierarchy login chatgpt
```

Or use the Providers screen in the phone app. Grok uses device-code OAuth;
ChatGPT uses the Codex login shown by the service status unless HTTP mode was
explicitly selected.

- **Grok OAuth** → `https://api.x.ai/v1` with the access token
- **ChatGPT OAuth** → Codex device flow (`chatgpt.com/backend-api/codex`)

Health: `GET /api/health` (no token). Everything else requires `Authorization: Bearer $HIERARCHY_TOKEN` when the token is set.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/demo.py
```
