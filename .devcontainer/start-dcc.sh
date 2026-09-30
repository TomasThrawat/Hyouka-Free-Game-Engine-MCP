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

echo "== Codespaces forwarding =="
echo "Ports 9765/9797 are declared public in .devcontainer/devcontainer.json."

echo "DCC MCP runtime ready"
echo "BLENDER_PUBLIC_URL=https://${CODESPACE_NAME}-9765.app.github.dev/mcp"
echo "KRITA_PUBLIC_URL=https://${CODESPACE_NAME}-9797.app.github.dev/mcp"
echo "BLENDER_INTERNAL=127.0.0.1:18765/mcp"
echo "KRITA_INTERNAL=127.0.0.1:19797/mcp"
