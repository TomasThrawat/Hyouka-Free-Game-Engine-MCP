#!/usr/bin/env bash
set -Eeuo pipefail

echo "== Node =="
node --version
npm --version

echo "== Install dependencies =="
npm install --no-fund --no-audit

echo "== Next.js build =="
npm run build

echo "== Dependency audit =="
npm audit --omit=dev --audit-level=high

echo "== Validate unified remote MCP registry =="
python3 - <<'PY'
import json
from pathlib import Path

p = Path("runtime/free-mcp-providers.json")
registry = json.loads(p.read_text())
providers = registry.get("providers", [])
by_id = {provider.get("id"): provider for provider in providers}

assert by_id.get("blender-mcp"), "Missing blender-mcp provider"
assert by_id.get("krita-mcp"), "Missing krita-mcp provider"

for provider_id in ("blender-mcp", "krita-mcp"):
    provider = by_id[provider_id]
    assert provider.get("enabled") is True
    assert provider.get("dynamicDiscovery") is True
    assert provider.get("discoveryProtocol") == "MCP tools/list"
    assert provider.get("urlEnv"), f"{provider_id} missing urlEnv"
    assert provider.get("tokenEnv"), f"{provider_id} missing tokenEnv"
    assert "urlFile" not in provider
    assert "urlFileKey" not in provider
    assert "authType" not in provider
    assert "runtimeManifestUrl" not in provider
    assert "runtimeManifestKey" not in provider

assert not any(provider.get("id") in {"blender-dcc", "krita"} for provider in providers)
print("Unified remote MCP registry validated: Blender MCP + Krita MCP are ordinary remote providers.")
PY

echo "== Validate unified MCP route wiring =="
python3 - <<'PY'
from pathlib import Path

route = Path("app/api/mcp/route.ts").read_text()
assert "discoverRemoteMcpTools" in route
assert "registerRemoteMcpTools" in route
assert "remoteMcpToolInventory" in route
assert '"godot_mcp_inventory"' in route
assert "godot_blender_discover_tools" not in route
assert "godot_krita_discover_tools" not in route
assert "godot_blender_status" not in route
assert "godot_krita_status" not in route
print("Unified MCP route validated: Godot + remote discovery + unified inventory tool.")
PY

echo "== Validate official Godot CLI manifest =="
python3 - <<'PY'
import json
from pathlib import Path
p = Path("runtime/godot-official-cli.json")
m = json.loads(p.read_text())
flags = m.get("flags", [])
assert m.get("engine") == "Godot"
assert m.get("version") == "4.7.2-stable"
assert m.get("source", {}).get("repository") == "https://github.com/godotengine/godot"
assert m.get("source", {}).get("ref") == "4.7.2-stable"
assert m.get("count") == 116 == len(flags)
assert len(flags) == len(set(flags))
assert "--export-" not in flags
assert all(isinstance(f, str) and f.startswith("-") for f in flags)
assert "--screen" in flags
print("Official CLI manifest validated: 116 unique switches")
PY

echo "== Python bridge =="
python3 -m py_compile godot/public_bridge.py
echo "Python bridge syntax validation passed."

echo "== Godot smoke project =="
test -f runtime/godot-smoke-test/project.godot
test -f runtime/godot-smoke-test/main.tscn
test -f runtime/godot-smoke-test/smoke.gd
echo "Godot smoke project files validated."

echo "== Install download tools =="
sudo apt-get update
sudo apt-get install -y curl unzip

echo "== Download official Godot .NET =="
curl -fL --retry 8 -o /tmp/godot.zip https://github.com/godotengine/godot/releases/download/4.7.2-stable/Godot_v4.7.2-stable_mono_linux_x86_64.zip
curl -fL --retry 8 -o /tmp/SHA512-SUMS.txt https://github.com/godotengine/godot/releases/download/4.7.2-stable/SHA512-SUMS.txt

echo "== Verify Godot checksum =="
CHECKSUM=$(grep -E '[[:space:]]Godot_v4.7.2-stable_mono_linux_x86_64.zip$' /tmp/SHA512-SUMS.txt | awk '{print $1}')
test -n "$CHECKSUM"
printf '%s  /tmp/godot.zip
' "$CHECKSUM" | sha512sum -c -

echo "== Verify Godot .NET runtime =="
rm -rf /tmp/godot
mkdir -p /tmp/godot
unzip -oq /tmp/godot.zip -d /tmp/godot
GODOT_DIR=$(find /tmp/godot -maxdepth 1 -type d -name 'Godot_v4.7.2-stable_mono_linux_x86_64' -print -quit)
test -n "$GODOT_DIR"
test -d "$GODOT_DIR/GodotSharp/Api/Debug/"

GODOT_BIN=$(find "$GODOT_DIR" -maxdepth 1 -type f -name 'Godot_v4.7.2-stable_mono_linux*' -print -quit)
test -n "$GODOT_BIN"
chmod +x "$GODOT_BIN"
"$GODOT_BIN" --version
"$GODOT_BIN" --headless --path runtime/godot-smoke-test --editor --quit
echo "Godot editor/headless initialization passed."

echo "== Run Godot runtime smoke test =="
"$GODOT_BIN" --headless --path runtime/godot-smoke-test
echo "Godot runtime smoke test completed successfully."

echo "== Verify engine boundary =="
if grep -RniE 'O3DE|o3de|[Bb]lender/' app godot 2>/dev/null; then
  echo "Unexpected external-engine reference found in app/godot source."
  exit 1
fi

echo "== CI checks passed =="
