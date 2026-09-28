# Hyouka O3DE HTTP MCP

A Vercel-hosted Streamable HTTP MCP gateway for the open-source Open 3D Engine (O3DE).

## Full callable-tool gateway

The MCP is designed around **dynamic tool discovery**, not a hard-coded list.

It can discover and invoke:

- all top-level commands dynamically detected from `scripts/o3de.py`
- callable Python scripts in O3DE script/tool trees
- O3DE shell scripts under script/tool trees
- built O3DE executables found in the engine/tool/build trees
- CMake `add_executable` targets
- CMake `add_custom_target` targets
- CTest `add_test(NAME ...)` registrations
- long-running/background tools with process tracking
- current tool `--help` output

The MCP surface is:

- `o3de_discover_tools`
- `o3de_find_tools`
- `o3de_probe_tool`
- `o3de_invoke_tool`
- `o3de_build_target`
- `o3de_processes`
- `o3de_stop_process`
- `o3de_cli`
- `o3de_cli_help`
- `o3de_status`

The older individual top-level shortcuts remain for compatibility.

## Important meaning of "all"

O3DE also contains C++ classes, components, editor APIs, and internal functions that are not independently executable interfaces. Those are not fabricated into fake MCP tools.

Instead, every callable artifact discoverable from the installed O3DE tree is addressable through a stable `toolId` and the universal dispatcher.

Newly built executables and newly added Python/CMake tools become discoverable without changing the Vercel route.

## Architecture

ChatGPT / MCP client
-> Composio
-> Vercel Streamable HTTP MCP
-> HTTPS O3DE universal bridge
-> dynamic O3DE inventory
-> scripts / executables / CMake / CTest
-> O3DE

Vercel is the protocol/control layer. The O3DE process runs on a separate host because Vercel Functions are not a persistent O3DE installation.

## Runtime configuration

Bridge:

- `O3DE_ROOT`: O3DE source/installation root
- `O3DE_WORKSPACE_ROOT`: allowed working-directory boundary
- `O3DE_BUILD_DIR`: configured CMake/CTest build tree
- `O3DE_BRIDGE_PORT`: default `9765`
- `O3DE_BRIDGE_TOKEN`: recommended for public bridge URLs

Vercel:

- `O3DE_BRIDGE_URL`
- `O3DE_BRIDGE_TOKEN`
- optionally `O3DE_BRIDGE_CONFIG_URL`

The default runtime manifest is `runtime/o3de-bridge.json`.

## Safety model

The bridge:

- uses argv arrays and `shell=False`
- validates and limits arguments
- restricts command cwd to `O3DE_WORKSPACE_ROOT`
- restricts discovered callable files to the O3DE engine root
- excludes third-party/cache trees
- supports an optional shared bearer token

## Source

The gateway was built from the O3DE source repository:

https://github.com/o3de/o3de

The source audit covered O3DE script/tool directories plus targeted searches for Python entry points, Asset Processor, Project Manager, CMake tool targets, and automated testing.
