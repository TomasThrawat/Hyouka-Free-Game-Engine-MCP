# Hyouka O3DE HTTP MCP

Vercel-hosted Streamable HTTP MCP gateway for Open 3D Engine (O3DE).

## Live O3DE runtime

The repository now includes a GitHub Actions workflow named **O3DE Live Bridge**.

When dispatched, it:

1. installs the official O3DE 26.05 Linux Debian package
2. starts the secure public O3DE CLI bridge on port 9765
3. verifies O3DE with `--version` and `get-registered`
4. creates a temporary HTTPS Cloudflare Quick Tunnel
5. publishes the live bridge URL to `runtime/o3de-bridge.json`
6. keeps the runtime alive for the selected duration

The Vercel MCP reads that manifest dynamically, so no Vercel code change is needed when the temporary tunnel URL changes.

Cloudflare documents Quick Tunnels as temporary development/testing tunnels. They generate a random `trycloudflare.com` hostname and do not provide an uptime guarantee. citeturn331166search0

## MCP capabilities

The MCP exposes dynamic O3DE tooling:

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

The compatibility top-level shortcuts are retained.

## Public runtime mode

Without a bridge credential, the live public runtime is intentionally limited to first-party O3DE top-level CLI tools.

`o3de_invoke_tool` can execute discovered IDs such as:

`o3de-cli:get-global-project`
`o3de-cli:get-registered`
`o3de-cli:register`

Arbitrary shell scripts, arbitrary executables, CMake builds, CTest execution, and background processes remain blocked in public mode. They are available through the full private bridge when a securely managed `O3DE_BRIDGE_TOKEN` is configured.

## Architecture

ChatGPT / MCP client
-> Composio
-> Vercel Streamable HTTP MCP
-> runtime/o3de-bridge.json
-> HTTPS O3DE bridge
-> O3DE 26.05

## Runtime limitations

The GitHub Actions runtime is temporary. It stops when the workflow ends or is cancelled. The Quick Tunnel URL also changes on each run. For a persistent production runtime, replace the Quick Tunnel with a managed Cloudflare Tunnel or another persistent HTTPS host. Cloudflare recommends named/managed tunnels for production use. citeturn331166search1turn331166search6

## Source

O3DE source repository:

https://github.com/o3de/o3de

Official Linux package:

https://o3debinaries.org/download/linux.html
