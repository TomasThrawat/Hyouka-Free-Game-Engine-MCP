#!/usr/bin/env bash
set -Eeuo pipefail

BLENDER_BIN="/usr/local/bin/blender"
DCC_SITE="/opt/dcc-mcp-python"
KRITA_DIR="/opt/krita-mcp"
KRITA_VENV="/opt/krita-mcp-venv"
ROOT="/workspaces/Hyouka-Free-Game-Engine-MCP"

: "${HYOUKA_DCC_MCP_TOKEN:?HYOUKA_DCC_MCP_TOKEN must be available as a Codespaces secret}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN must be available inside the Codespace}"
: "${CODESPACE_NAME:?CODESPACE_NAME must be available inside the Codespace}"

echo "== Stop previous DCC processes =="
for pattern in "blender_bootstrap.py" "krita_mcp_http.py" "Xvfb :99"; do
  pkill -f "${pattern}" 2>/dev/null || true
done
sudo nginx -s stop 2>/dev/null || true

echo "== Start Xvfb for headless Krita =="
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  nohup Xvfb :99 -screen 0 1280x800x24 -nolisten tcp > /tmp/hyouka-xvfb.log 2>&1 &
fi
export DISPLAY=:99

echo "== Start headless Blender MCP =="
if ! pgrep -f "blender.*blender_bootstrap.py" >/dev/null 2>&1; then
  nohup env PYTHONPATH="${DCC_SITE}" "${BLENDER_BIN}" --background --python "${ROOT}/.devcontainer/blender_bootstrap.py" > /tmp/hyouka-blender-mcp.log 2>&1 &
fi

echo "== Start Krita =="
if ! pgrep -x "krita" >/dev/null 2>&1; then
  nohup krita --nosplash > /tmp/hyouka-krita.log 2>&1 &
fi

echo "== Wait for Krita plugin =="
KRITA_READY=0
for i in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:5678/health >/tmp/krita-health.json 2>/dev/null; then
    KRITA_READY=1
    break
  fi
  sleep 1
done

if [[ "$KRITA_READY" -ne 1 ]]; then
  echo "Krita plugin did not become healthy."
  sed -n '1,220p' /tmp/hyouka-krita.log || true
  exit 1
fi
echo "Krita plugin health passed:"
cat /tmp/krita-health.json

echo "== Start Krita Streamable HTTP MCP =="
if ! pgrep -f "krita_mcp_http.py" >/dev/null 2>&1; then
  nohup env KRITA_URL="http://127.0.0.1:5678" "${KRITA_VENV}/bin/python" "${ROOT}/.devcontainer/krita_mcp_http.py" > /tmp/hyouka-krita-mcp.log 2>&1 &
fi

echo "== Wait for MCP processes =="
BLENDER_READY=0
for i in $(seq 1 90); do
  if (echo > /dev/tcp/127.0.0.1/18765) >/dev/null 2>&1; then
    BLENDER_READY=1
    break
  fi
  sleep 1
done

KRITA_MCP_READY=0
for i in $(seq 1 90); do
  if (echo > /dev/tcp/127.0.0.1/19797) >/dev/null 2>&1; then
    KRITA_MCP_READY=1
    break
  fi
  sleep 1
done

if [[ "$BLENDER_READY" -ne 1 ]]; then
  echo "Blender MCP internal port did not open."
  sed -n '1,260p' /tmp/hyouka-blender-mcp.log || true
  exit 1
fi

if [[ "$KRITA_MCP_READY" -ne 1 ]]; then
  echo "Krita MCP internal port did not open."
  sed -n '1,260p' /tmp/hyouka-krita-mcp.log || true
  exit 1
fi

echo "== Configure protected reverse proxy =="
sudo tee /tmp/hyouka-dcc-nginx.conf >/dev/null <<EOF
worker_processes  1;
pid /tmp/hyouka-dcc-nginx.pid;
events {
  worker_connections 1024;
}
http {
  map \$http_authorization \$mcp_authorized {
    default 0;
    "Bearer ${HYOUKA_DCC_MCP_TOKEN}" 1;
  }

  server {
    listen 9765;
    server_name _;

    location / {
      if (\$mcp_authorized = 0) { return 401; }
      proxy_pass http://127.0.0.1:18765;
      proxy_http_version 1.1;
      proxy_buffering off;
      proxy_cache off;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
      proxy_set_header Host \$host;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
  }

  server {
    listen 9797;
    server_name _;

    location / {
      if (\$mcp_authorized = 0) { return 401; }
      proxy_pass http://127.0.0.1:19797;
      proxy_http_version 1.1;
      proxy_buffering off;
      proxy_cache off;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
      proxy_set_header Host \$host;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
  }
}
EOF

sudo nginx -t -c /tmp/hyouka-dcc-nginx.conf
sudo nginx -c /tmp/hyouka-dcc-nginx.conf

echo "== Configure public Codespaces forwarding =="
command -v gh >/dev/null 2>&1 || { echo "GitHub CLI is required but was not installed."; exit 1; }

PORT_VISIBILITY_OK=0
for attempt in $(seq 1 20); do
  if GH_TOKEN="${GITHUB_TOKEN}" gh codespace ports visibility 9765:public 9797:public -c "${CODESPACE_NAME}" >/tmp/hyouka-ports-visibility.log 2>&1; then
    PORT_VISIBILITY_OK=1
    break
  fi
  echo "Port visibility attempt ${attempt}/20 failed; retrying..."
  tail -n 20 /tmp/hyouka-ports-visibility.log || true
  sleep 2
done

if [[ "$PORT_VISIBILITY_OK" -ne 1 ]]; then
  echo "Direct Codespaces port visibility failed; starting authenticated Actions relay."

  RELAY_SECRET="HYOUKA_DCC_CODESPACE_GH_TOKEN"
  RELAY_WORKFLOW=".github/workflows/dcc-port-visibility-relay.yml"
  relay_exit=0

  if ! printf '%s' "$GITHUB_TOKEN" | gh secret set "$RELAY_SECRET" -R "$GITHUB_REPOSITORY"; then
    echo "Failed to store the temporary Codespaces token as a repository secret."
    cat /tmp/hyouka-ports-visibility.log || true
    exit 1
  fi

  cleanup_relay_secret() {
    gh secret delete "$RELAY_SECRET" -R "$GITHUB_REPOSITORY" --yes >/dev/null 2>&1 || true
  }
  trap cleanup_relay_secret EXIT

  if ! gh workflow run "$RELAY_WORKFLOW" -R "$GITHUB_REPOSITORY" --ref main -f codespace_name="$CODESPACE_NAME"; then
    echo "Failed to dispatch the DCC port visibility relay workflow."
    exit 1
  fi

  relay_run_id=""
  for attempt in $(seq 1 30); do
    relay_run_id="$(gh run list -R "$GITHUB_REPOSITORY" --workflow "$RELAY_WORKFLOW" --branch main --limit 1 --json databaseId --jq '.[0].databaseId // empty' 2>/dev/null || true)"
    if [[ -n "$relay_run_id" ]]; then
      break
    fi
    sleep 2
  done

  if [[ -z "$relay_run_id" ]]; then
    echo "Could not resolve the relay workflow run ID."
    exit 1
  fi

  set +e
  gh run watch "$relay_run_id" -R "$GITHUB_REPOSITORY" --exit-status
  relay_exit=$?
  set -e

  if [[ "$relay_exit" -ne 0 ]]; then
    echo "DCC port visibility relay failed."
    exit "$relay_exit"
  fi

  echo "DCC public port relay completed successfully."
fi

echo "== Verify public Codespaces forwarding =="
PORTS_JSON="$(GH_TOKEN="${GITHUB_TOKEN}" gh codespace ports -c "${CODESPACE_NAME}" --json sourcePort,visibility,browseUrl)"
python3 -c '
import json, sys
ports = json.loads(sys.argv[1])
expected = {9765, 9797}
seen = {int(p["sourcePort"]) for p in ports if int(p["sourcePort"]) in expected}
visibility = {int(p["sourcePort"]): p["visibility"] for p in ports if int(p["sourcePort"]) in expected}
missing = expected - seen
bad = {port: value for port, value in visibility.items() if value != "public"}
if missing or bad:
    raise SystemExit(f"Port visibility verification failed: missing={sorted(missing)}, bad={bad}")
for port in sorted(expected):
    print(f"{port}: {visibility[port]}")
' "$PORTS_JSON"

echo "DCC MCP runtime ready"
echo "BLENDER_PUBLIC_URL=https://${CODESPACE_NAME}-9765.app.github.dev/mcp"
echo "KRITA_PUBLIC_URL=https://${CODESPACE_NAME}-9797.app.github.dev/mcp"
echo "BLENDER_INTERNAL=127.0.0.1:18765/mcp"
echo "KRITA_INTERNAL=127.0.0.1:19797/mcp"
