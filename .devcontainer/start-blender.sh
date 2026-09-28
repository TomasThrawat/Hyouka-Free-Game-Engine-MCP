#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/blender_output" "$ROOT/runtime"
CLOUDFLARED="$HOME/.local/bin/cloudflared"

pkill -f "blender --background --python .*blender/server.py" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:9765" 2>/dev/null || true

nohup blender --background --python "$ROOT/blender/server.py" > /tmp/hyouka-blender.log 2>&1 &
echo $! > /tmp/hyouka-blender.pid

for _ in $(seq 1 45); do
  if curl -fsS http://127.0.0.1:9765/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:9765/health >/dev/null 2>&1; then
  echo "Blender bridge failed to start"
  tail -n 120 /tmp/hyouka-blender.log || true
  exit 1
fi

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared binary missing: $CLOUDFLARED"
  exit 1
fi

nohup "$CLOUDFLARED" tunnel --no-autoupdate --url http://127.0.0.1:9765 > /tmp/hyouka-cloudflared.log 2>&1 &
echo $! > /tmp/hyouka-cloudflared.pid

TUNNEL_URL=""
for _ in $(seq 1 60); do
  TUNNEL_URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/hyouka-cloudflared.log 2>/dev/null | head -n 1 || true)"
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "Cloudflare Quick Tunnel URL was not detected"
  tail -n 160 /tmp/hyouka-cloudflared.log || true
  exit 1
fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PAYLOAD="$(python3 - "$TUNNEL_URL" "$NOW" <<'PY'
import json, sys
print(json.dumps({
  "status": "ok",
  "engine": "Blender",
  "url": sys.argv[1],
  "createdAt": sys.argv[2],
  "transport": "http",
  "runtime": "GitHub Codespaces",
  "policy": "free-only-no-pc"
}, separators=(",", ":")))
PY
)"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  REPO="TomasThrawat/Hyouka-Free-Game-Engine-MCP"
  FILE="runtime/blender-bridge.json"
  ENCODED="$(printf '%s' "$PAYLOAD" | base64 -w 0)"
  SHA="$(gh api "repos/$REPO/contents/$FILE" --jq '.sha' 2>/dev/null || true)"
  if [ -n "$SHA" ]; then
    gh api --method PUT "repos/$REPO/contents/$FILE"       -H "Accept: application/vnd.github+json"       -f message="chore: update Blender quick tunnel"       -f content="$ENCODED"       -f sha="$SHA" >/tmp/hyouka-tunnel-push.log 2>&1 || {
        echo "Failed to publish tunnel URL to GitHub"
        cat /tmp/hyouka-tunnel-push.log || true
      }
  else
    echo "Could not read runtime/blender-bridge.json SHA"
  fi
else
  echo "GitHub CLI is not authenticated; tunnel URL will remain local: $TUNNEL_URL"
fi

echo "Blender bridge: http://127.0.0.1:9765"
echo "Public Blender bridge: $TUNNEL_URL"
