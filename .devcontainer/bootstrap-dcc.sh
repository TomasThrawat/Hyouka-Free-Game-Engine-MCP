#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/Hyouka-Free-Game-Engine-MCP"
LOCK_FILE="/tmp/hyouka-dcc-bootstrap.lock"
LOG_FILE="/tmp/hyouka-dcc-bootstrap.log"
READY_FILE="/opt/hyouka-dcc-install-complete"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "DCC bootstrap already running; leaving existing process in place."
  exit 0
fi

echo "DCC bootstrap started at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [[ ! -f "$READY_FILE" ]]; then
  echo "== Install DCC dependencies =="
  bash "$ROOT/.devcontainer/install-dcc.sh"
  sudo touch "$READY_FILE"
  sudo chmod 0644 "$READY_FILE"
fi

echo "== Start DCC runtime =="
bash "$ROOT/.devcontainer/start-dcc.sh"
echo "DCC bootstrap completed at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
