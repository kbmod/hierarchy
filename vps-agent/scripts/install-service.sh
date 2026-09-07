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

if [ ! -d "$ROOT/src/hierarchy" ]; then
  echo "expected $ROOT/src/hierarchy" >&2
  exit 1
fi

mkdir -p "$HOME_DIR"
chmod 700 "$HOME_DIR"

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
  # keep existing token; refresh paths
  TOKEN="$(. "$ENV_FILE"; printf '%s' "${HIERARCHY_TOKEN:-}")"
  grep -q '^HIERARCHY_HOME=' "$ENV_FILE" || echo "HIERARCHY_HOME=$HOME_DIR" >>"$ENV_FILE"
  if grep -q '^PYTHONPATH=' "$ENV_FILE"; then
    sed -i "s|^PYTHONPATH=.*|PYTHONPATH=$ROOT/src|" "$ENV_FILE"
  else
    echo "PYTHONPATH=$ROOT/src" >>"$ENV_FILE"
  fi
fi

cat >"$UNIT" <<EOF
[Unit]
Description=Hierarchy agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
WorkingDirectory=$ROOT
ExecStart=$PYTHON -m hierarchy serve --host 0.0.0.0 --port 8765
Restart=always
RestartSec=2
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now hierarchy.service

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
echo
echo "Status:  systemctl status hierarchy"
echo "Logs:    journalctl -u hierarchy -f"
if [ "$CREATED_TOKEN" = 0 ]; then
  echo "(reused token from $ENV_FILE)"
fi
