#!/usr/bin/env bash
set -Eeuo pipefail

BLENDER_BIN="/usr/local/bin/blender"
DCC_SITE="/opt/dcc-mcp-python"
KRITA_VENV="/opt/krita-mcp-venv"
ROOT="/workspaces/Hyouka-Free-Game-Engine-MCP"
MANIFEST_API="https://api.github.com/repos/${GITHUB_REPOSITORY}/contents/runtime/dcc-live.json"
STAGE="init"

publish_runtime_failure() {
  local stage="$1"
  local rc="$2"
  local current current_sha content payload
  set +e
  current="$(curl -fsS \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "${MANIFEST_API}?ref=main" 2>/dev/null || true)"
  current_sha="$(printf '%s' "${current}" | jq -r '.sha // empty' 2>/dev/null || true)"
  cat > /tmp/dcc-live.json <<EOF
{
  "version": "1.0.0",
  "status": "error",
  "runtime": "github-codespaces-public-port-or-cloudflare",
  "updatedAt": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "error": "runtime_failed",
  "stage": "${stage}",
  "exitCode": ${rc},
  "providers": {
    "blender-dcc": {"status": "offline", "url": null},
    "krita": {"status": "offline", "url": null}
  }
}
EOF
  content="$(base64 -w0 /tmp/dcc-live.json 2>/dev/null || true)"
  if [[ -n "${current_sha}" ]]; then
    payload="$(jq -n \
      --arg message "chore: publish DCC runtime failure status [skip ci]" \
      --arg content "${content}" \
      --arg sha "${current_sha}" \
      '{message:$message,content:$content,sha:$sha,branch:"main"}' 2>/dev/null || true)"
  else
    payload="$(jq -n \
      --arg message "chore: publish DCC runtime failure status [skip ci]" \
      --arg content "${content}" \
      '{message:$message,content:$content,branch:"main"}' 2>/dev/null || true)"
  fi
  if [[ -n "${payload}" ]]; then
    curl -fsS -X PUT \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -H "Content-Type: application/json" \
      --data "${payload}" \
      "${MANIFEST_API}" >/tmp/dcc-live-failure-publish.json 2>&1 || true
  fi
}

on_runtime_exit() {
  local rc=$?
  if [[ "$rc" -eq 0 ]]; then
    return 0
  fi
  local failed_stage="${STAGE}"
  trap - EXIT
  set +e
  echo "DCC runtime failed at stage=${failed_stage} exit=${rc}."
  publish_runtime_failure "${failed_stage}" "${rc}"
  exit "${rc}"
}
trap on_runtime_exit EXIT


if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  if [[ -n "${GH_TOKEN:-}" ]]; then
    export GITHUB_TOKEN="$GH_TOKEN"
  elif command -v gh >/dev/null 2>&1; then
    GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
    export GITHUB_TOKEN
  fi
fi

: "${HYOUKA_DCC_MCP_TOKEN:?HYOUKA_DCC_MCP_TOKEN must be available as a Codespaces secret}"
: "${CODESPACE_NAME:?CODESPACE_NAME must be available inside the Codespace}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN must be available inside the Codespace}"

STAGE="stop_previous_processes"
echo "== Stop previous DCC processes =="
for pattern in "blender_bootstrap.py" "krita_mcp_http.py" "Xvfb :99"; do
  pkill -f "${pattern}" 2>/dev/null || true
done
sudo nginx -s stop 2>/dev/null || true

STAGE="verify_github_token"
echo "== Verify Codespaces GitHub token =="
case "${GITHUB_TOKEN}" in
  "") echo "GITHUB_TOKEN is empty." >&2; exit 1 ;;
  *) echo "GITHUB_TOKEN is available for runtime manifest publishing." ;;
esac
STAGE="start_xvfb"
echo "== Start Xvfb for headless Krita =="
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  nohup Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >/tmp/hyouka-xvfb.log 2>&1 &
fi
export DISPLAY=:99

STAGE="start_blender"
echo "== Start headless Blender MCP =="
if ! pgrep -f "blender.*blender_bootstrap.py" >/dev/null 2>&1; then
  nohup env PYTHONPATH="${DCC_SITE}" "${BLENDER_BIN}" --background --python "${ROOT}/.devcontainer/blender_bootstrap.py" >/tmp/hyouka-blender-mcp.log 2>&1 &
fi

STAGE="start_krita"
echo "== Start Krita =="
if ! pgrep -x "krita" >/dev/null 2>&1; then
  nohup krita --nosplash >/tmp/hyouka-krita.log 2>&1 &
fi

STAGE="wait_krita_plugin"
echo "== Wait for Krita plugin =="
KRITA_READY=0
for i in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:5678/health >/tmp/krita-health.json 2>/dev/null; then
    KRITA_READY=1
    break
  fi
  sleep 1
done

if [[ "${KRITA_READY}" -ne 1 ]]; then
  echo "Krita plugin did not become healthy."
  sed -n '1,220p' /tmp/hyouka-krita.log || true
  exit 1
fi

echo "Krita plugin health passed:"
cat /tmp/krita-health.json

STAGE="start_krita_mcp"
echo "== Start Krita Streamable HTTP MCP =="
if ! pgrep -f "krita_mcp_http.py" >/dev/null 2>&1; then
  nohup env KRITA_URL="http://127.0.0.1:5678" "${KRITA_VENV}/bin/python" "${ROOT}/.devcontainer/krita_mcp_http.py" >/tmp/hyouka-krita-mcp.log 2>&1 &
fi

STAGE="wait_internal_mcp"
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

if [[ "${BLENDER_READY}" -ne 1 ]]; then
  echo "Blender MCP internal port did not open."
  sed -n '1,260p' /tmp/hyouka-blender-mcp.log || true
  exit 1
fi

if [[ "${KRITA_MCP_READY}" -ne 1 ]]; then
  echo "Krita MCP internal port did not open."
  sed -n '1,260p' /tmp/hyouka-krita-mcp.log || true
  exit 1
fi

STAGE="configure_nginx"
echo "== Configure protected reverse proxy =="
sudo tee /tmp/hyouka-dcc-nginx.conf >/dev/null <<EOF
worker_processes 1;
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
  server {
    listen 9888;
    server_name _;

    location /blender/ {
      proxy_pass http://127.0.0.1:9765/;
      proxy_http_version 1.1;
      proxy_buffering off;
      proxy_cache off;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
      proxy_set_header Host \$host;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location /krita/ {
      proxy_pass http://127.0.0.1:9797/;
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

BLENDER_PUBLIC_URL=""
KRITA_PUBLIC_URL=""

STAGE="start_cloudflared"
echo "== Start Cloudflare Quick Tunnel =="
rm -f /tmp/hyouka-cloudflared.log
nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:9888 >/tmp/hyouka-cloudflared.log 2>&1 &
CLOUDFLARED_PID=$!
echo "cloudflared pid=${CLOUDFLARED_PID}"
TUNNEL_URL=""
for attempt in $(seq 1 60); do
  TUNNEL_URL="$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' /tmp/hyouka-cloudflared.log | sed -n '1p' || true)"
  if [[ -n "${TUNNEL_URL}" ]]; then break; fi
  if ! kill -0 "${CLOUDFLARED_PID}" 2>/dev/null; then
    echo "cloudflared exited before publishing a tunnel URL."
    sed -n "1,220p" /tmp/hyouka-cloudflared.log || true
    break
  fi
  sleep 2
done
if [[ -n "${TUNNEL_URL}" ]]; then
  BLENDER_PUBLIC_URL="${TUNNEL_URL}/blender/mcp"
  KRITA_PUBLIC_URL="${TUNNEL_URL}/krita/mcp"
  echo "Cloudflare tunnel: ${TUNNEL_URL}"
fi

if [[ -z "${BLENDER_PUBLIC_URL}" || -z "${KRITA_PUBLIC_URL}" ]]; then
  echo "Cloudflare public DCC tunnel was not established."
  exit 1
fi


STAGE="probe_tunnel"
echo "== Verify protected public MCP endpoints =="
for URL in "${BLENDER_PUBLIC_URL}" "${KRITA_PUBLIC_URL}"; do
  CODE="$(curl -sS -o /tmp/hyouka-tunnel-probe.json -w '%{http_code}' -H "Authorization: Bearer ${HYOUKA_DCC_MCP_TOKEN}" -H 'Accept: application/json, text/event-stream' "${URL}" || true)"
  case "${CODE}" in
    200|400|405) echo "${URL}: HTTP ${CODE}" ;;
    *) echo "${URL}: unexpected HTTP ${CODE}"; cat /tmp/hyouka-tunnel-probe.json 2>/dev/null || true; exit 1 ;;
  esac
done
STAGE="publish_manifest"
echo "== Publish live DCC runtime manifest =="
cat >/tmp/dcc-live.json <<EOF
{
  "version": "1.0.0",
  "status": "online",
  "runtime": "github-codespaces-public-port-or-cloudflare",
  "updatedAt": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "providers": {
    "blender-dcc": {
      "status": "online",
      "url": "${BLENDER_PUBLIC_URL}"
    },
    "krita": {
      "status": "online",
      "url": "${KRITA_PUBLIC_URL}"
    }
  }
}
EOF

MANIFEST_API="https://api.github.com/repos/${GITHUB_REPOSITORY}/contents/runtime/dcc-live.json"
MANIFEST_B64="$(base64 -w0 /tmp/dcc-live.json)"
PUBLISHED=0

for attempt in $(seq 1 8); do
  CURRENT_JSON="$(curl -fsS \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "${MANIFEST_API}?ref=main" || true)"
  CURRENT_SHA="$(printf '%s' "$CURRENT_JSON" | jq -r '.sha // empty')"

  if [[ -n "$CURRENT_SHA" ]]; then
    PAYLOAD="$(jq -n \
      --arg message "chore: publish live DCC MCP runtime manifest [skip ci]" \
      --arg content "$MANIFEST_B64" \
      --arg sha "$CURRENT_SHA" \
      '{message:$message,content:$content,sha:$sha,branch:"main"}')"
  else
    PAYLOAD="$(jq -n \
      --arg message "chore: publish live DCC MCP runtime manifest [skip ci]" \
      --arg content "$MANIFEST_B64" \
      '{message:$message,content:$content,branch:"main"}')"
  fi

  HTTP_CODE="$(curl -sS \
    -o /tmp/dcc-live-update.json \
    -w '%{http_code}' \
    -X PUT \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -H 'Content-Type: application/json' \
    --data "$PAYLOAD" \
    "${MANIFEST_API}")"

  case "$HTTP_CODE" in
    200|201)
      PUBLISHED=1
      break
      ;;
    409|422)
      echo "Manifest update conflict on attempt ${attempt}; retrying..."
      sleep 2
      ;;
    *)
      echo "Manifest update failed with HTTP ${HTTP_CODE}."
      cat /tmp/dcc-live-update.json || true
      exit 1
      ;;
  esac
done

if [[ "$PUBLISHED" -ne 1 ]]; then
  echo "Live DCC manifest could not be published."
  exit 1
fi

echo "DCC live manifest published successfully."
echo "BLENDER_PUBLIC_URL=${BLENDER_PUBLIC_URL}"
echo "KRITA_PUBLIC_URL=${KRITA_PUBLIC_URL}"
