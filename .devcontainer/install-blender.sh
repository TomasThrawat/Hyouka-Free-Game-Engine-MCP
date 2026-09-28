#!/usr/bin/env bash
set -euo pipefail

if ! command -v blender >/dev/null 2>&1; then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y blender
fi

mkdir -p blender_output
