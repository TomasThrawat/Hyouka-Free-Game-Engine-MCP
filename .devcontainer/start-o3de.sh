#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export O3DE_ROOT="\${O3DE_ROOT:-/opt/O3DE/26.05}"
export O3DE_SCRIPT="\${O3DE_SCRIPT:-\${O3DE_ROOT}/scripts/o3de.py}"
export O3DE_PYTHON="\${O3DE_PYTHON:-\${O3DE_ROOT}/python/python.sh}"
export O3DE_WORKSPACE_ROOT="\${O3DE_WORKSPACE_ROOT:-\${REPO_ROOT}}"
export O3DE_BRIDGE_PORT="\${O3DE_BRIDGE_PORT:-9765}"

LOG_FILE="/tmp/hyouka-o3de-bridge.log"
PID_FILE="/tmp/hyouka-o3de-bridge.pid"
MANIFEST="\${REPO_ROOT}/runtime/o3de-bridge.json"

test -f "\${O3DE_ROOT}/engine.json"
test -f "\${O3DE_ROOT}/scripts/o3de.sh"

if [[ -f "\${PID_FILE}" ]]; then
  old_pid="$(cat "\${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "\${old_pid}" ]] && kill -0 "\${old_pid}" 2>/dev/null; then
    echo "[O3DE] Bridge already running (PID \${old_pid})."
  else
    rm -f "\${PID_FILE}"
  fi
fi

if [[ ! -f "\${PID_FILE}" ]]; then
  nohup env \
    O3DE_ROOT="\${O3DE_ROOT}" \
    O3DE_SCRIPT="\${O3DE_SCRIPT}" \
    O3DE_PYTHON="\${O3DE_PYTHON}" \
    O3DE_WORKSPACE_ROOT="\${O3DE_WORKSPACE_ROOT}" \
    O3DE_BRIDGE_PORT="\${O3DE_BRIDGE_PORT}" \
    python3 "\${REPO_ROOT}/o3de/public_bridge.py" >"\${LOG_FILE}" 2>&1 &
  echo $! >"\${PID_FILE}"
fi

healthy=0
for _ in \$(seq 1 45); do
  if curl -fsS "http://127.0.0.1:\${O3DE_BRIDGE_PORT}/health" >/tmp/hyouka-o3de-health.json 2>/dev/null; then
    healthy=1
    cat /tmp/hyouka-o3de-health.json
    break
  fi
  sleep 1
done

if (( healthy == 0 )); then
  echo "[O3DE] Bridge failed to become healthy." >&2
  cat "\${LOG_FILE}" >&2 || true
  exit 1
fi

curl -fsS "http://127.0.0.1:\${O3DE_BRIDGE_PORT}/selftest" >/tmp/hyouka-o3de-selftest.json
cat /tmp/hyouka-o3de-selftest.json

python3 - <<'PY'
import json
data = json.load(open("/tmp/hyouka-o3de-selftest.json"))
assert data["status"] == "ok", data
assert data["engineMetadata"]["version"], data
assert data["getRegistered"]["returnCode"] == 0, data
assert data["topLevelCommandCount"] >= 20, data
PY

if ! command -v gh >/dev/null 2>&1; then
  echo "[O3DE] GitHub CLI is required for public Codespaces port forwarding." >&2
  exit 1
fi

if [[ -z "\${CODESPACE_NAME:-}" ]]; then
  echo "[O3DE] CODESPACE_NAME is missing." >&2
  exit 1
fi

echo "[O3DE] Making port \${O3DE_BRIDGE_PORT} public..."
gh codespace ports visibility "\${O3DE_BRIDGE_PORT}:public" -c "\${CODESPACE_NAME}"

BRIDGE_URL="https://\${CODESPACE_NAME}-\${O3DE_BRIDGE_PORT}.app.github.dev"

curl -fsS "\${BRIDGE_URL}/health" >/tmp/hyouka-o3de-public-health.json
curl -fsS "\${BRIDGE_URL}/selftest" >/tmp/hyouka-o3de-public-selftest.json

cat /tmp/hyouka-o3de-public-health.json
cat /tmp/hyouka-o3de-public-selftest.json

git -C "\${REPO_ROOT}" fetch origin main
git -C "\${REPO_ROOT}" reset --hard origin/main

VERSION="$(python3 -c 'import json; print(json.load(open("/opt/O3DE/26.05/engine.json")).get("version","unknown"))')"

jq -n \
  --arg url "\${BRIDGE_URL}" \
  --arg codespace "\${CODESPACE_NAME}" \
  --arg version "\${VERSION}" \
  '{
    status: "ok",
    engine: "O3DE",
    url: $url,
    transport: "http",
    tokenRequired: false,
    mode: "public-cli-only",
    runtime: "GitHub Codespaces O3DE 26.05",
    codespace: $codespace,
    version: $version,
    capabilities: [
      "first-party O3DE top-level CLI",
      "dynamic CLI discovery",
      "CLI help probing",
      "safe universal invoke for o3de-cli:*"
    ],
    notes: "Codespace-backed runtime. Port becomes private again after restart and must be republished by this startup script."
  }' > "\${MANIFEST}"

git -C "\${REPO_ROOT}" config user.name "github-codespaces[bot]"
git -C "\${REPO_ROOT}" config user.email "github-codespaces[bot]@users.noreply.github.com"

git -C "\${REPO_ROOT}" add runtime/o3de-bridge.json
git -C "\${REPO_ROOT}" diff --cached --quiet || \
  git -C "\${REPO_ROOT}" commit -m "chore: publish live Codespaces O3DE bridge [skip ci]"
git -C "\${REPO_ROOT}" push origin HEAD:main

echo "[O3DE] LIVE BRIDGE: \${BRIDGE_URL}"
