#!/bin/bash
# Install Hierarchy as a systemd service so it keeps running after you log out.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
ENV_FILE=/etc/hierarchy.env
UNIT=/etc/systemd/system/hierarchy.service
HOME_DIR=/var/lib/hierarchy

PARSED_ENV_VALUE=""
read_env_value() {
  local key="$1" raw
  PARSED_ENV_VALUE=""
  raw="$(awk -v key="$key" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' "$ENV_FILE")"
  [ -n "$raw" ] || return 1
  case "$raw" in
    \"*\") PARSED_ENV_VALUE="${raw:1:${#raw}-2}" ;;
    \'*\') PARSED_ENV_VALUE="${raw:1:${#raw}-2}" ;;
    *\"*|*\'*) return 2 ;;
    *) PARSED_ENV_VALUE="$raw" ;;
  esac
  [ -n "$PARSED_ENV_VALUE" ] || return 3
}

EXISTING_SERVICE_USER=""
EXISTING_CHATGPT_BACKEND=""
EXISTING_CODEX_BIN=""
EXISTING_CODEX_HOME=""
if [ -e "$ENV_FILE" ]; then
  if [ -L "$ENV_FILE" ]; then
    echo "refusing symlinked environment file: $ENV_FILE" >&2
    exit 1
  fi
  if [ ! -f "$ENV_FILE" ]; then
    echo "environment path is not a regular file: $ENV_FILE" >&2
    exit 1
  fi
  for key in HIERARCHY_SERVICE_USER HIERARCHY_CHATGPT_BACKEND HIERARCHY_CODEX_BIN HIERARCHY_CODEX_HOME; do
    if read_env_value "$key"; then
      if [ "$key" = HIERARCHY_SERVICE_USER ]; then EXISTING_SERVICE_USER="$PARSED_ENV_VALUE"
      elif [ "$key" = HIERARCHY_CHATGPT_BACKEND ]; then EXISTING_CHATGPT_BACKEND="$PARSED_ENV_VALUE"
      elif [ "$key" = HIERARCHY_CODEX_BIN ]; then EXISTING_CODEX_BIN="$PARSED_ENV_VALUE"
      else EXISTING_CODEX_HOME="$PARSED_ENV_VALUE"
      fi
    else
      status=$?
      if [ "$status" -ne 1 ]; then
        echo "malformed $key assignment in $ENV_FILE" >&2
        exit 1
      fi
    fi
  done
fi

# Never install the agent as root.  With sudo, SUDO_USER is the operator who owns the
# Codex login and is therefore the safest default for the service account too.
SERVICE_USER="${HIERARCHY_SERVICE_USER:-${EXISTING_SERVICE_USER:-${SUDO_USER:-}}}"
if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = root ]; then
  echo "refusing a root/unknown service user; set HIERARCHY_SERVICE_USER or run via sudo" >&2
  exit 1
fi
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "unknown HIERARCHY_SERVICE_USER: $SERVICE_USER" >&2
  exit 1
fi
SERVICE_UID="$(id -u "$SERVICE_USER")"
if [ "$SERVICE_UID" -eq 0 ]; then
  echo "refusing to install hierarchy.service for uid 0 ($SERVICE_USER)" >&2
  exit 1
fi
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | awk -F: 'NR == 1 { print $6 }')"
if [ -z "$SERVICE_HOME" ] || [ "$SERVICE_HOME" = / ]; then
  echo "could not resolve a usable home directory for $SERVICE_USER" >&2
  exit 1
fi

if [ ! -d "$ROOT/src/hierarchy" ]; then
  echo "expected $ROOT/src/hierarchy" >&2
  exit 1
fi
if ! runuser -u "$SERVICE_USER" -- test -r "$ROOT/src/hierarchy" -a -x "$ROOT/src/hierarchy"; then
  echo "$SERVICE_USER cannot read/traverse $ROOT/src/hierarchy" >&2
  exit 1
fi
if [ -L "$HOME_DIR" ]; then
  echo "refusing symlinked hierarchy home: $HOME_DIR" >&2
  exit 1
fi
install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$HOME_DIR"

CODEX_BIN="${HIERARCHY_CODEX_BIN:-${EXISTING_CODEX_BIN:-}}"
if [ -n "$CODEX_BIN" ]; then
  if [ ! -x "$CODEX_BIN" ] || [ -d "$CODEX_BIN" ]; then
    echo "HIERARCHY_CODEX_BIN is not an executable file: $CODEX_BIN" >&2
    exit 1
  fi
else
  # Prefer the service user's normal per-user installation, then a system install.
  # This checks paths only; it never opens auth.json or any other credential file.
  if [ -x "$SERVICE_HOME/.local/bin/codex" ] && [ ! -d "$SERVICE_HOME/.local/bin/codex" ]; then
    CODEX_BIN="$SERVICE_HOME/.local/bin/codex"
  elif command -v codex >/dev/null 2>&1; then
    CODEX_BIN="$(command -v codex)"
  fi
fi

CODEX_HOME="${HIERARCHY_CODEX_HOME:-${EXISTING_CODEX_HOME:-}}"
if [ -n "$CODEX_HOME" ] && [ -z "$CODEX_BIN" ]; then
  echo "HIERARCHY_CODEX_HOME requires an executable HIERARCHY_CODEX_BIN or an installed codex" >&2
  exit 1
fi
if [ -n "$CODEX_BIN" ]; then
  CODEX_HOME="${CODEX_HOME:-$SERVICE_HOME/.codex}"
  case "$CODEX_HOME" in
    /*) ;;
    *) echo "HIERARCHY_CODEX_HOME must be an absolute path: $CODEX_HOME" >&2; exit 1 ;;
  esac
  if [ -L "$CODEX_HOME" ] || { [ -e "$CODEX_HOME" ] && [ ! -d "$CODEX_HOME" ]; }; then
    echo "HIERARCHY_CODEX_HOME must be a real directory: $CODEX_HOME" >&2
    exit 1
  fi
  if [ ! -e "$CODEX_HOME" ]; then
    install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$CODEX_HOME"
  elif ! runuser -u "$SERVICE_USER" -- test -r "$CODEX_HOME" -a -x "$CODEX_HOME"; then
    echo "$SERVICE_USER cannot read/traverse HIERARCHY_CODEX_HOME: $CODEX_HOME" >&2
    exit 1
  fi
  if ! runuser -u "$SERVICE_USER" -- test -x "$CODEX_BIN"; then
    echo "$SERVICE_USER cannot execute HIERARCHY_CODEX_BIN: $CODEX_BIN" >&2
    exit 1
  fi
fi

# A previous root-installed service may have left state files behind.  Limit the
# ownership migration to this exact, validated service directory; chown does not
# follow symlinks in the directory tree.
find "$HOME_DIR" -xdev -exec chown --no-dereference "$SERVICE_USER:$SERVICE_GROUP" {} +

set_env_line() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "/^${key}=/c\\${key}=${value}" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

remove_env_line() {
  local key="$1"
  sed -i "/^${key}=/d" "$ENV_FILE"
}

if [ -L "$ENV_FILE" ]; then
  echo "refusing symlinked environment file: $ENV_FILE" >&2
  exit 1
fi
if [ ! -f "$ENV_FILE" ]; then
  TOKEN="$(openssl rand -hex 24)"
  umask 077
  cat >"$ENV_FILE" <<EOF
HIERARCHY_TOKEN=$TOKEN
HIERARCHY_HOME=$HOME_DIR
PYTHONPATH=$ROOT/src
EOF
  chmod 600 "$ENV_FILE"
  CREATED_TOKEN=1
else
  CREATED_TOKEN=0
  # Keep only the existing Hierarchy token. Never execute an environment file as root.
  if ! read_env_value HIERARCHY_TOKEN; then
    echo "$ENV_FILE has no non-empty HIERARCHY_TOKEN" >&2
    exit 1
  fi
  TOKEN="$PARSED_ENV_VALUE"
fi

set_env_line HIERARCHY_HOME "$HOME_DIR"
set_env_line PYTHONPATH "$ROOT/src"
set_env_line HIERARCHY_SERVICE_USER "$SERVICE_USER"
set_env_line HIERARCHY_SERVICE_GROUP "$SERVICE_GROUP"
set_env_line HIERARCHY_SERVICE_HOME "$SERVICE_HOME"
set_env_line HIERARCHY_CHATGPT_BACKEND "${HIERARCHY_CHATGPT_BACKEND:-${EXISTING_CHATGPT_BACKEND:-auto}}"
if [ -n "$CODEX_BIN" ]; then
  set_env_line HIERARCHY_CODEX_BIN "$CODEX_BIN"
  set_env_line HIERARCHY_CODEX_HOME "$CODEX_HOME"
else
  remove_env_line HIERARCHY_CODEX_BIN
  remove_env_line HIERARCHY_CODEX_HOME
fi
chmod 600 "$ENV_FILE"
chown root:root "$ENV_FILE"

cat >"$UNIT" <<EOF
[Unit]
Description=Hierarchy agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
Environment=HOME=$SERVICE_HOME
Environment=PATH=$SERVICE_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=$ROOT
ExecStart=$PYTHON -m hierarchy serve --host 0.0.0.0 --port 8765
User=$SERVICE_USER
Group=$SERVICE_GROUP
Restart=always
RestartSec=2
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hierarchy.service
if ! systemctl restart hierarchy.service; then
  echo "failed to restart hierarchy.service after installing the updated service configuration" >&2
  exit 1
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
TS_IP=""
TS_DNS=""
if command -v tailscale >/dev/null 2>&1; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  TS_DNS="$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || true)"
fi
echo
echo "Hierarchy is running in the background (closing SSH is fine)."
if [ -n "$TS_IP" ]; then
  echo "  Tailscale URL: http://${TS_IP}:8765"
  if [ -n "$TS_DNS" ]; then
    echo "  MagicDNS URL:  http://${TS_DNS}:8765"
  fi
  echo "  Use the Tailscale URL from the phone (install Tailscale on the phone too)."
  echo "  No public firewall port needed if you only reach this box over Tailscale."
else
  echo "  URL:   http://${IP:-YOUR_VPS_IP}:8765"
  echo "  Open TCP 8765 on the firewall / security group."
fi
echo "  Token: $TOKEN"
echo "  Service user: $SERVICE_USER ($SERVICE_GROUP), HOME=$SERVICE_HOME"
if [ -n "$CODEX_BIN" ]; then
  echo "  Codex runtime: $CODEX_BIN (CODEX_HOME=$CODEX_HOME)"
  echo "  Authenticate Codex as $SERVICE_USER; Codex owns auth.json refresh and rotation."
  echo "  Codex runs unattended in isolated bot workdirs; approval/escalation requests are denied."
else
  echo "  Codex runtime: not detected (Grok/API-key installs are unchanged)"
fi
echo
echo "Status:  systemctl status hierarchy"
echo "Logs:    journalctl -u hierarchy -f"
if [ "$CREATED_TOKEN" = 0 ]; then
  echo "(reused token from $ENV_FILE)"
fi
