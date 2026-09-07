#!/bin/sh
set -eu
cd /workspace
node scripts/preview.mjs stop || true
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/api/health; then
  :
else
  STORE=/tmp/hierarchy-store
  mkdir -p "$STORE"
  if [ -n "${XAI_API_KEY:-}" ]; then
    PYTHONPATH=/workspace/vps-agent/src python3 -m hierarchy key xai "$XAI_API_KEY" --store "$STORE" >/tmp/hierarchy-key.log 2>&1 || true
  fi
  PYTHONPATH=/workspace/vps-agent/src python3 -m hierarchy serve --host 127.0.0.1 --port 8765 --store "$STORE" >>/tmp/hierarchy-agent.log 2>&1 &
  i=0
  while [ "$i" -lt 20 ]; do
    if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8765/api/health; then
      curl -sf -o /dev/null -X POST http://127.0.0.1:8765/api/floor -H "Content-Type: application/json" -d '{}' || true
      break
    fi
    i=$((i + 1))
    sleep 0.2
  done
fi
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi
npm run dev >>/tmp/app-startup.log 2>&1 &
