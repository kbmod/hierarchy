# Hierarchy

A Grok Bot–style floor of always-on teammates. They live on **your** computers (one or more VPS hosts), not a rented cloud desktop.

Message them like coworkers. They keep working after you leave the app. Sign in with **Grok (xAI) OAuth** or **ChatGPT OAuth**, or paste an API key.

The Android APK is the main client. A desktop shell comes later. This repo also has a web preview of the same UI.

## What you get

- Named bots (Atlas / Forge / Scout / Quill, or your own)
- A real computer on the VPS: shell, files, HTTP, bot-to-bot DMs
- Work continues in the background (jobs + routines)
- Take over the computer for passwords / 2FA, then return control
- One or more agent backends (primary + backups)
- Device-code OAuth for Grok and ChatGPT; tokens stay on the VPS

## Android APK

```bash
npm install
bash scripts/build-apk.sh
```

The debug APK is written to `dist-apk/hierarchy-debug.apk` (and `public/hierarchy-debug.apk` for sideload from the web preview).

On the phone: allow install from this source, open Hierarchy, add your VPS URL + token, then connect Grok or ChatGPT.

## VPS agent (the computer)

On each server, run it as a service (no open terminal):

```bash
git clone https://github.com/kbmod/hierarchy.git
cd hierarchy/vps-agent
sudo bash scripts/install-service.sh
sudo bash scripts/install-hermes-runtime.sh
```

Paste the printed URL (`http://YOUR_VPS_IP:8765`) and token into the app. Open TCP 8765 on the firewall.

```bash
python3 -m hierarchy key xai "$XAI_API_KEY"
python3 -m hierarchy login grok
python3 -m hierarchy login chatgpt
```

Or use Providers in the app (device-code OAuth). The Hermes installer pins the
reviewed upstream runtime, imports any existing Grok/Codex grants into Hermes's
private credential store, and enables per-bot autonomous tool turns. It requires
`git`, `uv`, and systemd on the VPS.

- **Grok OAuth** → Hermes `xai-oauth`
- **ChatGPT OAuth** → Hermes `openai-codex` using ChatGPT subscription access

Health: `GET /api/health` (no token). Everything else requires `Authorization: Bearer $HIERARCHY_TOKEN` when the token is set.

## Web preview

```bash
npm install
npm run dev
```

Use agent URL `demo` to talk to a local agent on this machine.

## Tests

```bash
cd vps-agent
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/demo.py
```
