#!/bin/bash
# Install the pinned upstream Hermes gateway used by Hierarchy's Bot runtime.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

HERMES_REPO=https://github.com/NousResearch/hermes-agent.git
HERMES_COMMIT=966637323e6f90864e069dbc12755934c2c86387
INSTALL_ROOT=/opt/hierarchy/hermes-agent
HERMES_HOME=/var/lib/hierarchy/hermes
HIERARCHY_ENV=/etc/hierarchy.env
UNIT=/etc/systemd/system/hierarchy-hermes.service
SOURCE_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

if [ ! -f "$HIERARCHY_ENV" ] || [ -L "$HIERARCHY_ENV" ]; then
  echo "Install Hierarchy first; expected regular file $HIERARCHY_ENV" >&2
  exit 1
fi
SERVICE_USER="$(awk -F= '$1 == "HIERARCHY_SERVICE_USER" {print $2; exit}' "$HIERARCHY_ENV")"
SERVICE_GROUP="$(awk -F= '$1 == "HIERARCHY_SERVICE_GROUP" {print $2; exit}' "$HIERARCHY_ENV")"
if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = root ] || ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Invalid HIERARCHY_SERVICE_USER in $HIERARCHY_ENV" >&2
  exit 1
fi
SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}" 
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | awk -F: 'NR == 1 {print $6}')"
UV_BIN="$(runuser -u "$SERVICE_USER" -- sh -lc 'command -v uv' 2>/dev/null || true)"
if [ -z "$UV_BIN" ]; then
  echo "uv is required for the pinned Hermes install" >&2
  exit 1
fi

install -d -m 755 -o "$SERVICE_USER" -g "$SERVICE_GROUP" /opt/hierarchy
if [ ! -d "$INSTALL_ROOT/.git" ]; then
  if [ -e "$INSTALL_ROOT" ]; then
    echo "Refusing to replace non-git path $INSTALL_ROOT" >&2
    exit 1
  fi
  runuser -u "$SERVICE_USER" -- git clone --filter=blob:none "$HERMES_REPO" "$INSTALL_ROOT"
fi
runuser -u "$SERVICE_USER" -- git -C "$INSTALL_ROOT" fetch origin "$HERMES_COMMIT"
runuser -u "$SERVICE_USER" -- git -C "$INSTALL_ROOT" checkout --detach "$HERMES_COMMIT"
runuser -u "$SERVICE_USER" -- env UV_LINK_MODE=copy "$UV_BIN" sync --frozen --no-dev --project "$INSTALL_ROOT"
# The API-server gateway adapter uses aiohttp, which upstream currently keeps
# in its messaging extra even when it is the only enabled platform.
runuser -u "$SERVICE_USER" -- env UV_LINK_MODE=copy "$UV_BIN" pip install \
  --python "$INSTALL_ROOT/.venv/bin/python" 'aiohttp==3.14.3'

install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$HERMES_HOME"
HERMES_KEY_FILE="$HERMES_HOME/.hierarchy-api-key"
if [ ! -s "$HERMES_KEY_FILE" ]; then
  umask 077
  openssl rand -base64 36 | tr -d '\n' >"$HERMES_KEY_FILE"
fi
chown "$SERVICE_USER:$SERVICE_GROUP" "$HERMES_KEY_FILE"
chmod 600 "$HERMES_KEY_FILE"

# Configure the one gateway listener. Named bot profiles are routed through
# /p/<profile>/ and receive their own API keys when Hierarchy creates them.
runuser -u "$SERVICE_USER" -- env \
  HERMES_HOME="$HERMES_HOME" \
  HERMES_KEY_FILE="$HERMES_KEY_FILE" \
  "$INSTALL_ROOT/.venv/bin/python" - <<'PY'
import os
from pathlib import Path
import yaml

home = Path(os.environ["HERMES_HOME"])
path = home / "config.yaml"
try:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
except (OSError, ValueError, TypeError):
    config = {}
if not isinstance(config, dict):
    config = {}
gateway = config.setdefault("gateway", {})
gateway["multiplex_profiles"] = True
gateway["api_server"] = {
    "enabled": True,
    "host": "127.0.0.1",
    "port": 8642,
    "key": Path(os.environ["HERMES_KEY_FILE"]).read_text(encoding="utf-8").strip(),
    "max_concurrent_runs": 10,
}
agent = config.setdefault("agent", {})
agent["max_turns"] = None
agent["bot_mode_protocol"] = True
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY

# Seed Hermes's own auth store from already-authorized local clients. Hermes
# copies these grants and then owns its refresh chain; it never shares a live
# writable auth file with Codex or Hierarchy.
runuser -u "$SERVICE_USER" -- env \
  HOME="$SERVICE_HOME" HERMES_HOME="$HERMES_HOME" CODEX_HOME="$SERVICE_HOME/.codex" \
  HIERARCHY_HOME=/var/lib/hierarchy \
  "$INSTALL_ROOT/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

from hermes_cli.auth import _import_codex_cli_tokens, _save_codex_tokens
from hermes_cli.auth_xai import _save_xai_oauth_tokens

codex = _import_codex_cli_tokens()
if codex:
    _save_codex_tokens(codex)

source = Path(os.environ["HIERARCHY_HOME"]) / "auth.json"
try:
    data = json.loads(source.read_text(encoding="utf-8"))
    grok = (data.get("oauth") or {}).get("grok") or {}
except (OSError, ValueError, TypeError):
    grok = {}
if grok.get("access_token") and grok.get("refresh_token"):
    _save_xai_oauth_tokens(
        {
            "access_token": grok["access_token"],
            "refresh_token": grok["refresh_token"],
            "token_type": grok.get("token_type") or "Bearer",
        },
        set_active=False,
    )
PY

set_env_line() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$HIERARCHY_ENV"; then
    sed -i "/^${key}=/c\\${key}=${value}" "$HIERARCHY_ENV"
  else
    printf '%s=%s\n' "$key" "$value" >>"$HIERARCHY_ENV"
  fi
}
set_env_line HIERARCHY_AGENT_BACKEND hermes
set_env_line HIERARCHY_HERMES_BIN "$INSTALL_ROOT/.venv/bin/hermes"
set_env_line HIERARCHY_HERMES_HOME "$HERMES_HOME"
set_env_line HIERARCHY_HERMES_URL http://127.0.0.1:8642
set_env_line HIERARCHY_HERMES_TURN_TIMEOUT 3600
chmod 600 "$HIERARCHY_ENV"
chown root:root "$HIERARCHY_ENV"

# Give Hermes terminal tools a narrow, non-secret control command for creating
# and messaging persistent Hierarchy bots. Do not source /etc/hierarchy.env:
# that file also contains the phone API bearer token, which agents do not need.
cat >/usr/local/bin/hierarchy-bot <<EOF
#!/bin/sh
export PYTHONPATH='$SOURCE_ROOT/src'
export HIERARCHY_HOME='/var/lib/hierarchy'
export HIERARCHY_AGENT_BACKEND='hermes'
export HIERARCHY_HERMES_BIN='$INSTALL_ROOT/.venv/bin/hermes'
export HIERARCHY_HERMES_HOME='$HERMES_HOME'
export HIERARCHY_HERMES_URL='http://127.0.0.1:8642'
export HIERARCHY_HERMES_TURN_TIMEOUT='3600'
exec /usr/bin/python3 -m hierarchy bot "\$@"
EOF
chmod 755 /usr/local/bin/hierarchy-bot
chown root:root /usr/local/bin/hierarchy-bot

cat >"$UNIT" <<EOF
[Unit]
Description=Hermes Bot runtime for Hierarchy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=HOME=$SERVICE_HOME
Environment=HERMES_HOME=$HERMES_HOME
Environment=PATH=$INSTALL_ROOT/.venv/bin:$SERVICE_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=$INSTALL_ROOT
ExecStart=$INSTALL_ROOT/.venv/bin/hermes gateway run
User=$SERVICE_USER
Group=$SERVICE_GROUP
Restart=always
RestartSec=2
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

# Make ordering explicit without coupling Hierarchy's availability to a failed
# provider login: it starts after Hermes, while both retain independent restart.
install -d -m 755 /etc/systemd/system/hierarchy.service.d
cat >/etc/systemd/system/hierarchy.service.d/hermes.conf <<EOF
[Unit]
After=hierarchy-hermes.service
Wants=hierarchy-hermes.service
EOF

systemctl daemon-reload
systemctl enable hierarchy-hermes.service
systemctl restart hierarchy-hermes.service
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8642/health >/dev/null; then
    break
  fi
  sleep 1
done
if ! curl -fsS http://127.0.0.1:8642/health >/dev/null; then
  systemctl status hierarchy-hermes.service --no-pager -l >&2 || true
  exit 1
fi
systemctl restart hierarchy.service

echo "Hermes Bot runtime installed at pinned commit $HERMES_COMMIT"
echo "Gateway: active on loopback; Hierarchy now routes supported bots through Hermes"
