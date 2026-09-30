#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/Hyouka-Free-Game-Engine-MCP"
LOG_FILE="/tmp/hyouka-dcc-bootstrap.log"
PID_FILE="/tmp/hyouka-dcc-bootstrap.pid"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "DCC bootstrap already running (pid=$old_pid)."
    exit 0
  fi
fi

nohup setsid bash "$ROOT/.devcontainer/bootstrap-dcc.sh" >"$LOG_FILE" 2>&1 < /dev/null &
echo $! >"$PID_FILE"
echo "DCC bootstrap launched in background (pid=$!)."
