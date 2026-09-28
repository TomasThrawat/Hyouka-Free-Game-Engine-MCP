#!/usr/bin/env bash
set -euo pipefail

O3DE_VERSION="2605_0"
O3DE_ROOT="/opt/O3DE/26.05"
DEB_PATH="/tmp/o3de_\${O3DE_VERSION}.deb"
DEB_URL="https://o3debinaries.org/main/Latest/Linux/o3de_\${O3DE_VERSION}.deb"

echo "[O3DE] Disk before install:"
df -h /

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  wget \
  git \
  jq \
  python3 \
  python3-venv \
  python3-pip

if [[ ! -f "\${O3DE_ROOT}/engine.json" ]]; then
  echo "[O3DE] Downloading \${O3DE_VERSION}..."
  rm -f "\${DEB_PATH}"

  wget \
    --https-only \
    --tries=8 \
    --timeout=60 \
    --waitretry=5 \
    --continue \
    -O "\${DEB_PATH}" \
    "\${DEB_URL}"

  test -s "\${DEB_PATH}"

  echo "[O3DE] Installing package..."
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "\${DEB_PATH}"

  rm -f "\${DEB_PATH}"
fi

if [[ -x "\${O3DE_ROOT}/python/get_python.sh" ]]; then
  echo "[O3DE] Initializing bundled Python..."
  "\${O3DE_ROOT}/python/get_python.sh"
fi

"\${O3DE_ROOT}/scripts/o3de.sh" register --this-engine || true

test -f "\${O3DE_ROOT}/engine.json"
test -f "\${O3DE_ROOT}/scripts/o3de.py"
test -x "\${O3DE_ROOT}/scripts/o3de.sh"

python3 - <<'PY'
import json
from pathlib import Path
p = Path("/opt/O3DE/26.05/engine.json")
data = json.loads(p.read_text())
print("[O3DE] engine_version=", data.get("version"))
print("[O3DE] engine_name=", data.get("engine_name") or data.get("engineName"))
PY

echo "[O3DE] Disk after install:"
df -h /
echo "[O3DE] SDK ready."
