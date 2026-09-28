#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/cloudflared"
mkdir -p "$BIN_DIR"

if command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared already installed"
  exit 0
fi

if [ -x "$BIN" ]; then
  echo "cloudflared already installed at $BIN"
  exit 0
fi

ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64) ASSET="cloudflared-linux-amd64" ;;
  arm64) ASSET="cloudflared-linux-arm64" ;;
  armhf) ASSET="cloudflared-linux-arm" ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

URL="$(curl -fsSL https://api.github.com/repos/cloudflare/cloudflared/releases/latest   | python3 -c 'import json,sys; data=json.load(sys.stdin); asset=sys.argv[1]; print(next(x["browser_download_url"] for x in data["assets"] if x["name"] == asset))' "$ASSET")"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP"
install -m 0755 "$TMP" "$BIN"

echo "Installed cloudflared: $("$BIN" --version | head -n 1)"
