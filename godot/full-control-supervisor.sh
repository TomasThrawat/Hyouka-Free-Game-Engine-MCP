#!/usr/bin/env bash
set -Eeuo pipefail

TMP="${RUNNER_TEMP:-/tmp}"
LOG="$TMP/godot-full-control-tunnel.log"
PID_FILE="$TMP/godot-full-control-tunnel.pid"
URL_FILE="$TMP/godot-full-control-url"

start_tunnel() {
  rm -f "$LOG"
  ssh     -o StrictHostKeyChecking=no     -o UserKnownHostsFile=/dev/null     -o LogLevel=ERROR     -o ExitOnForwardFailure=yes     -o ServerAliveInterval=20     -o ServerAliveCountMax=3     -R 80:127.0.0.1:10002     nokey@localhost.run >"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
}

get_url() {
  grep -Eo 'https://[A-Za-z0-9.-]+\.lhr\.life' "$LOG" | tail -1 || true
}

probe() {
  local url="$1"
  curl -sS --max-time 15 -o /dev/null -w '%{http_code}'     -X POST "$url/mcp"     -H 'Content-Type: application/json'     -H 'Accept: application/json, text/event-stream'     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"supervisor","version":"1"}}}' || true
}

start_tunnel
LAST=""
LAST_PUBLISHED=""

while true; do
  URL="$(get_url)"
  STATUS=0
  if [ -n "$URL" ]; then
    STATUS="$(probe "$URL")"
  fi

  if [ "$STATUS" = "401" ]; then
    if [ "$URL" != "$LAST" ]; then
      printf '%s/mcp\n' "$URL" >"$URL_FILE"
      echo "GODOT_FULL_CONTROL_TUNNEL_READY=$URL/mcp"
      LAST="$URL"
    fi
  else
    echo "GODOT_FULL_CONTROL_TUNNEL_RESTART status=$STATUS"
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    start_tunnel
  fi

  if [ -f /tmp/godot-full-control-published ] && [ -s "$URL_FILE" ]; then
    CURRENT="$(cat "$URL_FILE")"
    if [ -n "$LAST_PUBLISHED" ] && [ "$CURRENT" != "$LAST_PUBLISHED" ]; then
      cd "${GITHUB_WORKSPACE:-$(pwd)}"
      git config user.name "github-actions[bot]"
      git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      git fetch origin main
      git reset --hard origin/main
      jq -n --arg url "$CURRENT" --arg run "${GITHUB_RUN_ID:-0}"         '{status:"ok",engine:"Godot Full Control",url:$url,runtime:"Fulviuus/godot-mcp HTTP",source:"https://github.com/Fulviuus/godot-mcp",ownerRunId:$run}'         > runtime/godot-full-control-bridge.json
      git add runtime/godot-full-control-bridge.json
      git commit -m "chore: refresh live Godot full-control endpoint [skip ci]" || true
      git push origin HEAD:main || true
    fi
    LAST_PUBLISHED="$CURRENT"
  fi

  sleep 30
done
