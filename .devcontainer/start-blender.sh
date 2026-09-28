#!/usr/bin/env bash
set -euo pipefail

mkdir -p blender_output

pkill -f "blender --background --python .*blender/server.py" 2>/dev/null || true

nohup blender --background --python blender/server.py > /tmp/hyouka-blender.log 2>&1 &
echo $! > /tmp/hyouka-blender.pid

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:9765/health >/dev/null 2>&1; then
    echo "Blender bridge ready on port 9765"
    exit 0
  fi
  sleep 1
done

echo "Blender bridge failed to start"
tail -n 120 /tmp/hyouka-blender.log || true
exit 1
