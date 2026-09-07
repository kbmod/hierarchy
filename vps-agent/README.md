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

# OAuth device login
python3 -m hierarchy login grok
python3 -m hierarchy login chatgpt
```

Or use the Providers screen in the phone app (device-code OAuth).

- **Grok OAuth** → `https://api.x.ai/v1` with the access token
- **ChatGPT OAuth** → Codex device flow (`chatgpt.com/backend-api/codex`)

Health: `GET /api/health` (no token). Everything else requires `Authorization: Bearer $HIERARCHY_TOKEN` when the token is set.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/demo.py
```
