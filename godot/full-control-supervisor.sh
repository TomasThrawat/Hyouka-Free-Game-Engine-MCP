#!/usr/bin/env bash
set -Eeuo pipefail

TMP="${RUNNER_TEMP:-/tmp}"
LOG="$TMP/godot-full-control-tunnel.log"
PID_FILE="$TMP/godot-full-control-tunnel.pid"
URL_FILE="$TMP/godot-full-control-url"
PROXY_PORT="${PROXY_PORT:-18081}"

start_tunnel() {
  rm -f "$LOG"
  ssh     -o StrictHostKeyChecking=no     -o UserKnownHostsFile=/dev/null     -o LogLevel=ERROR     -o ExitOnForwardFailure=yes     -o ServerAliveInterval=20     -o ServerAliveCountMax=3     -R 80:127.0.0.1:$PROXY_PORT     nokey@localhost.run >"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
}

get_url() {
  grep -Eo 'https://[A-Za-z0-9.-]+\.lhr\.life|https://[A-Za-z0-9.-]+\.localhost\.run' "$LOG" | tail -1 || true
}

probe() {
  local url="$1"
  curl -sS --max-time 15 -o /dev/null -w '%{http_code}' \
    -X POST "$url/mcp" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"supervisor","version":"1"}}}' || true
}

start_tunnel
LAST=""

while true; do
  URL="$(get_url)"
  STATUS=0
  if [ -n "$URL" ]; then STATUS="$(probe "$URL")"; fi

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

  sleep 30
done