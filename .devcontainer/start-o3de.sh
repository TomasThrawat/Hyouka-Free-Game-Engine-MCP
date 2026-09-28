#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export O3DE_ROOT="${O3DE_ROOT:-/opt/O3DE/26.05}"
export O3DE_SCRIPT="${O3DE_SCRIPT:-${O3DE_ROOT}/scripts/o3de.py}"
export O3DE_WORKSPACE_ROOT="${O3DE_WORKSPACE_ROOT:-${REPO_ROOT}}"
export O3DE_BRIDGE_PORT="${O3DE_BRIDGE_PORT:-9765}"

LOG_FILE="/tmp/hyouka-o3de-bridge.log"
PID_FILE="/tmp/hyouka-o3de-bridge.pid"

test -f "${O3DE_ROOT}/engine.json"
test -f "${O3DE_ROOT}/scripts/o3de.sh"

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "[O3DE] Public bridge already running (PID ${old_pid})."
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

nohup env   O3DE_ROOT="${O3DE_ROOT}"   O3DE_SCRIPT="${O3DE_SCRIPT}"   O3DE_WORKSPACE_ROOT="${O3DE_WORKSPACE_ROOT}"   O3DE_BRIDGE_PORT="${O3DE_BRIDGE_PORT}"   python3 "${REPO_ROOT}/o3de/public_bridge.py" >"${LOG_FILE}" 2>&1 &
BRIDGE_PID=$!
echo "${BRIDGE_PID}" >"${PID_FILE}"

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${O3DE_BRIDGE_PORT}/health" >/tmp/hyouka-o3de-health.json 2>/dev/null; then
    cat /tmp/hyouka-o3de-health.json
    if command -v gh >/dev/null 2>&1 && [[ -n "${CODESPACE_NAME:-}" ]]; then
      gh codespace ports visibility "${O3DE_BRIDGE_PORT}:public" -c "${CODESPACE_NAME}" >/tmp/hyouka-o3de-port.log 2>&1 || true
    fi
    echo "[O3DE] Public CLI bridge URL: https://${CODESPACE_NAME:-unknown}-${O3DE_BRIDGE_PORT}.app.github.dev"
    exit 0
  fi
  sleep 1
done

echo "[O3DE] Public bridge failed to become healthy." >&2
cat "${LOG_FILE}" >&2 || true
exit 1
