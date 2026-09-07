#!/bin/bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p public
tar -C vps-agent --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
  -czf public/hierarchy-agent.tgz .
echo "wrote public/hierarchy-agent.tgz"
