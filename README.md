# hierarchy

A small multi-bot runtime. Roster, isolated stores, in-process chat and DMs.

This is **not** Hermes Agent and does not call Hermes Bot Mode.

Each bot has its own directory. One process owns every bot. A DM is written to the target inbox and drained immediately.

## Run

```bash
PYTHONPATH=src python3 -m hierarchy serve --port 8765
```

http://127.0.0.1:8765

Store: `~/.hierarchy` (`HIERARCHY_HOME` overrides). Credentials: `~/.hierarchy/auth.json` (mode 600).

## Models

Offline stub is the default (no keys). Then:

```bash
# API keys
python3 -m hierarchy key xai "$XAI_API_KEY"
python3 -m hierarchy key openai "$OPENAI_API_KEY"
python3 -m hierarchy key openrouter "$OPENROUTER_API_KEY"

# OAuth device login (prints a URL + code, polls until you approve)
python3 -m hierarchy login grok
python3 -m hierarchy login chatgpt

python3 -m hierarchy status
python3 -m hierarchy use stub
```

The roster page can save keys and start the same device-code OAuth.

- **xAI / OpenAI / OpenRouter keys** → OpenAI-compatible `chat/completions`
- **Grok OAuth** → `https://api.x.ai/v1` with the access token (SuperGrok / Grok CLI public client)
- **ChatGPT OAuth** → Codex device flow, then `chatgpt.com/backend-api/codex` (ChatGPT subscription, not `api.openai.com`)

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/demo.py
```
