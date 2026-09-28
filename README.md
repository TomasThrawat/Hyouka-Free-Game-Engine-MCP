# Hyouka O3DE HTTP MCP

A Vercel-hosted Streamable HTTP MCP gateway for the open-source Open 3D Engine (O3DE).

## What is exposed

The MCP mirrors the first-party top-level CLI subcommands registered by the inspected `scripts/o3de.py` entry point:

- get-global-project
- set-global-project
- create-template
- create-from-template
- register
- register-show
- get-registered
- enable-gem
- disable-gem
- edit-engine-properties
- edit-project-properties
- edit-gem-properties
- sha256
- download
- export-project-configure
- export-project
- repo
- edit-repo-properties

There is also `o3de_commands`, `o3de_status`, and `o3de_cli_help`.

## Architecture

ChatGPT / MCP client
-> Composio
-> Vercel Streamable HTTP MCP
-> HTTPS O3DE bridge
-> `scripts/o3de.py`
-> O3DE installation

The Vercel function is only the protocol/control layer. It does not pretend to contain the O3DE engine itself.

## Bridge

Run `o3de/bridge.py` on a machine or Codespace that has an O3DE checkout.

Required environment:

- `O3DE_ROOT`: path to the O3DE checkout
- `O3DE_WORKSPACE_ROOT`: optional workspace boundary for command cwd
- `O3DE_BRIDGE_PORT`: optional HTTP port, default 9765

The bridge uses `subprocess.run(..., shell=False)`, an allowlisted O3DE command set, bounded argument sizes, and a workspace cwd boundary.

## Vercel configuration

The Vercel MCP reads:

`O3DE_BRIDGE_URL`

or, for a rotating runtime:

`O3DE_BRIDGE_CONFIG_URL`

The default config path is:

`runtime/o3de-bridge.json`

The config must contain `{"status":"ok","url":"https://..." }` before the MCP will use it.

## Source

O3DE source inspected for this adapter:
https://github.com/o3de/o3de/tree/development

The adapter was based on the first-party `scripts/o3de.py` command registrations, not invented command names.

## Endpoint

`/api/mcp`

Health:

`/health`
