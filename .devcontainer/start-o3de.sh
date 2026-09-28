#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export O3DE_ROOT="${O3DE_ROOT:-}"
export O3DE_WORKSPACE_ROOT="${O3DE_WORKSPACE_ROOT:-$ROOT}"

python3 "$ROOT/o3de/bridge.py" > /tmp/hyouka-o3de-bridge.log 2>&1 &
BRIDGE_PID=$!
trap 'kill "$BRIDGE_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:9765/health >/tmp/hyouka-o3de-health.json 2>/dev/null; then
    cat /tmp/hyouka-o3de-health.json
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:9765/health >/dev/null 2>&1; then
  echo "O3DE bridge failed to start"
  cat /tmp/hyouka-o3de-bridge.log || true
  exit 1
fi

wait "$BRIDGE_PID"
