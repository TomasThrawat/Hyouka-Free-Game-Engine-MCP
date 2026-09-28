#!/usr/bin/env bash
set -euo pipefail

O3DE_VERSION="2605_0"
O3DE_ROOT="/opt/O3DE/26.05"
DEB_PATH="/tmp/o3de_${O3DE_VERSION}.deb"
DEB_URL="https://o3debinaries.org/main/Latest/Linux/o3de_${O3DE_VERSION}.deb"

echo "[O3DE] Installing prerequisites..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl wget git git-lfs unzip jq python3 python3-venv python3-pip build-essential ninja-build pkg-config

if [[ ! -f "${O3DE_ROOT}/engine.json" ]]; then
  echo "[O3DE] Downloading Linux SDK ${O3DE_VERSION}..."
  rm -f "${DEB_PATH}"
  wget -q --show-progress -O "${DEB_PATH}" "${DEB_URL}"
  echo "[O3DE] Installing SDK..."
  sudo apt-get install -y "${DEB_PATH}"
fi

if [[ -x "${O3DE_ROOT}/python/get_python.sh" ]]; then
  echo "[O3DE] Initializing bundled Python..."
  "${O3DE_ROOT}/python/get_python.sh"
fi

if [[ -x "${O3DE_ROOT}/scripts/o3de.sh" ]]; then
  echo "[O3DE] Registering this engine..."
  "${O3DE_ROOT}/scripts/o3de.sh" register --this-engine || true
fi

test -f "${O3DE_ROOT}/engine.json"
test -f "${O3DE_ROOT}/scripts/o3de.py"
test -x "${O3DE_ROOT}/scripts/o3de.sh"
echo "[O3DE] version:"
"${O3DE_ROOT}/scripts/o3de.sh" --version || true
echo "[O3DE] runtime ready at ${O3DE_ROOT}"
