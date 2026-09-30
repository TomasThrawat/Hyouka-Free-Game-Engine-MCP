#!/usr/bin/env bash
set -Eeuo pipefail

BLENDER_VERSION="${BLENDER_VERSION}"
BLENDER_DIR="/opt/blender-${BLENDER_VERSION}"
BLENDER_ARCHIVE="/tmp/blender-${BLENDER_VERSION}-linux-x64.tar.xz"
DCC_SITE="/opt/dcc-mcp-python"
KRITA_DIR="/opt/krita-mcp"

export DEBIAN_FRONTEND=noninteractive

echo "== Install OS dependencies =="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl git gh nginx \
  python3 python3-pip python3-venv \
  xz-utils tar gzip unzip \
  xvfb xauth x11-utils \
  krita

echo "== Verify GitHub CLI =="
gh --version | head -n 1

echo "== Install Blender ${BLENDER_VERSION} =="
if [[ ! -x "${BLENDER_DIR}/blender" ]]; then
  sudo mkdir -p /opt
  curl -fL --retry 8 --retry-delay 2 \
    -o "${BLENDER_ARCHIVE}" \
    "https://download.blender.org/release/Blender5.2/blender-${BLENDER_VERSION}-linux-x64.tar.xz"

  sudo rm -rf "${BLENDER_DIR}"
  sudo tar -xJf "${BLENDER_ARCHIVE}" -C /opt
  sudo mv "/opt/blender-${BLENDER_VERSION}-linux-x64" "${BLENDER_DIR}"
fi

sudo ln -sfn "${BLENDER_DIR}/blender" /usr/local/bin/blender
blender --version | head -n 2

echo "== Install dcc-mcp-blender =="
sudo rm -rf "${DCC_SITE}"
sudo mkdir -p "${DCC_SITE}"
sudo python3 -m pip install --break-system-packages --no-cache-dir \
  --target "${DCC_SITE}" \
  "dcc-mcp-blender==0.2.12"

echo "== Install Krita MCP =="
sudo rm -rf "${KRITA_DIR}"
sudo git clone --depth 1 https://github.com/nanayax3/krita-mcp.git "${KRITA_DIR}"

python3 -m venv /opt/krita-mcp-venv
/opt/krita-mcp-venv/bin/pip install --upgrade pip
if [[ -f "${KRITA_DIR}/requirements.txt" ]]; then
  /opt/krita-mcp-venv/bin/pip install -r "${KRITA_DIR}/requirements.txt"
else
  /opt/krita-mcp-venv/bin/pip install mcp httpx
fi

echo "== Install Krita plugin =="
KRITA_PYK="/home/vscode/.local/share/krita/pykrita"
mkdir -p "${KRITA_PYK}"
cp -a "${KRITA_DIR}/krita-plugin/." "${KRITA_PYK}/"

DESKTOP_FILE="$(find "${KRITA_PYK}" -maxdepth 1 -type f -name '*.desktop' | head -n 1)"
test -n "$DESKTOP_FILE"
MODULE_NAME="$(awk -F= '/^X-KDE-Library=/{print $2; exit}' "$DESKTOP_FILE")"
test -n "$MODULE_NAME"

python3 - "$MODULE_NAME" <<'PY'
from pathlib import Path
import sys

module = sys.argv[1]
path = Path.home() / ".config" / "kritarc"
path.parent.mkdir(parents=True, exist_ok=True)

text = path.read_text() if path.exists() else ""
lines = text.splitlines()

section = None
section_seen = False
updated = False

for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped[1:-1]
        if section == "python":
            section_seen = True
    elif section == "python" and stripped.startswith("enable_") and "=" in stripped:
        key = stripped.split("=", 1)[0]
        if key == f"enable_{module}":
            lines[i] = f"enable_{module}=true"
            updated = True

if not section_seen:
    if lines and lines[-1].strip():
        lines.append("")
    lines.append("[python]")

if not updated:
    lines.append(f"enable_{module}=true")

path.write_text("\n".join(lines) + "\n")
print(f"Enabled Krita Python plugin: enable_{module}=true")
PY

echo "== Validate Blender MCP Python imports =="
PYTHONPATH="${DCC_SITE}" python3 - <<'PY'
from dcc_mcp_core import McpHttpConfig
from dcc_mcp_blender import BlenderHost
print("dcc-mcp-blender Python imports passed")
PY

echo "== Validate Krita FastMCP import =="
PYTHONPATH="${KRITA_DIR}" /opt/krita-mcp-venv/bin/python - <<'PY'
from server import mcp
print("Krita FastMCP server import passed:", type(mcp).__name__)
PY

echo "== DCC install completed =="
