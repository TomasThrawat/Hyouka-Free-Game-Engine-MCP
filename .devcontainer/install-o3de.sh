#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${O3DE_ROOT:-}" ]]; then
  echo "O3DE_ROOT is not set."
  echo "Set O3DE_ROOT to an existing O3DE checkout before starting the bridge."
  exit 0
fi

if [[ ! -f "$O3DE_ROOT/scripts/o3de.py" ]]; then
  echo "O3DE CLI not found at $O3DE_ROOT/scripts/o3de.py" >&2
  exit 1
fi

echo "Using O3DE root: $O3DE_ROOT"
python3 "$O3DE_ROOT/scripts/o3de.py" --help >/tmp/o3de-help.txt
head -n 40 /tmp/o3de-help.txt
