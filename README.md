# Hyouka O3DE HTTP MCP

A Vercel-hosted Streamable HTTP MCP gateway for the open-source Open 3D Engine (O3DE).

## Scope

This is no longer limited to `scripts/o3de.py` top-level commands.

The MCP now exposes:

- dynamic discovery of callable O3DE Python scripts
- O3DE shell scripts under the engine tool/script areas
- built O3DE executables
- first-party `scripts/o3de.py` commands
- CMake executable/custom targets found in O3DE tool trees
- help probing for discovered tools
- universal tool invocation by stable `toolId`
- background process start/stop
- CMake target builds

### MCP tools

- `o3de_discover_tools`
- `o3de_probe_tool`
- `o3de_invoke_tool`
- `o3de_cli`
- `o3de_build_target`
- `o3de_processes`
- `o3de_stop_process`
- `o3de_status`
- `o3de_cli_help`

The original top-level shortcuts remain available for compatibility.

## How "all tools" works

O3DE contains many C++ APIs and editor systems that are not independently callable processes. Those are not fabricated into fake MCP tools.

Instead, the bridge discovers every callable artifact it can execute from the installed tree:

`Python -> shell script -> executable -> O3DE CLI -> CMake target`

This means newly built O3DE tools can become MCP-addressable without modifying the Vercel route.

## Architecture

ChatGPT / MCP client
-> Composio
-> Vercel Streamable HTTP MCP
-> HTTPS O3DE universal bridge
-> dynamic O3DE inventory
-> scripts / tools / executables / CMake targets
-> O3DE

Vercel remains the protocol/control layer. O3DE itself runs on a separate host because Vercel Functions are not a persistent O3DE installation.

## Runtime configuration

Bridge host:

- `O3DE_ROOT`: O3DE source/installation root
- `O3DE_WORKSPACE_ROOT`: optional command working-directory boundary
- `O3DE_BUILD_DIR`: optional configured CMake build tree
- `O3DE_BRIDGE_PORT`: default `9765`
- `O3DE_BRIDGE_TOKEN`: recommended shared bearer token for public bridges

Vercel:

- `O3DE_BRIDGE_URL`
- `O3DE_BRIDGE_TOKEN`
- optionally `O3DE_BRIDGE_CONFIG_URL`

The default runtime manifest is `runtime/o3de-bridge.json`.

## Source basis

The adapter was built against the O3DE source repository:

https://github.com/o3de/o3de

The source audit covered the engine's script/tool trees and targeted searches for Python entry points, Asset Processor/Project Manager tooling, CMake targets, and automated testing.

## Endpoint

`/api/mcp`

Health:

`/health`

The MCP is live on Vercel even when no bridge is configured; in that state execution tools return `not_configured` rather than pretending the engine ran.
