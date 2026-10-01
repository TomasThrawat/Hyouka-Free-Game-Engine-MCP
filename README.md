# Hyouka Game Engine MCP

Vercel Streamable HTTP MCP gateway that exposes one unified MCP endpoint for the game-engine workflow.

## Unified MCP

The single endpoint is:

- `/api/mcp`

It combines:

- **Godot** bridge tools.
- **Blender MCP** tools discovered from a remote Streamable HTTP MCP server.
- **Krita MCP** tools discovered from a remote Streamable HTTP MCP server.
- Any other providers declared in `runtime/free-mcp-providers.json`.

Blender and Krita are ordinary **remote MCP providers**. The gateway does not install, launch, proxy, or host Blender or Krita desktop runtimes. There is no Codespace, DCC bootstrap, desktop-process dependency, or tunnel requirement in this integration.

## Remote Blender and Krita configuration

Set these server-side environment variables on the Vercel project:

- `HYOUKA_BLENDER_MCP_URL`: the reachable Streamable HTTP MCP endpoint for Blender.
- `HYOUKA_KRITA_MCP_URL`: the reachable Streamable HTTP MCP endpoint for Krita.
- `HYOUKA_BLENDER_MCP_TOKEN`: optional bearer token for the Blender MCP endpoint.
- `HYOUKA_KRITA_MCP_TOKEN`: optional bearer token for the Krita MCP endpoint.

The configured remote servers must already exist and be reachable over HTTP. The gateway only connects to them and dynamically calls MCP `tools/list`; it does not create those servers.

The repository includes the provider declarations in `runtime/free-mcp-providers.json`:

- `blender-mcp` -> `HYOUKA_BLENDER_MCP_URL`
- `krita-mcp` -> `HYOUKA_KRITA_MCP_URL`

Tool names registered by the gateway are provider-prefixed, so Blender and Krita tools cannot collide with Godot or other remote tools.

## Unified inventory

Call the `godot_mcp_inventory` tool through `/api/mcp` to inspect:

- Godot tool count.
- Every configured remote MCP provider.
- Whether Blender/Krita are configured.
- Whether each provider is connected.
- Dynamically discovered remote tool counts.
- The total unified tool count.

This inventory intentionally distinguishes **declared**, **configured**, and **connected** providers. A provider is not reported as connected merely because it exists in the registry.

## CI validation

The GitHub Actions build validates that Blender and Krita:

- are present as remote providers;
- use dynamic MCP `tools/list` discovery;
- use environment-based remote URLs;
- contain no DCC runtime manifest fields.

CI also validates that the unified `/api/mcp` route calls remote discovery, registers discovered tools, and exposes the unified inventory tool.

## Provider sources

- Blender MCP: https://github.com/dcc-mcp/dcc-mcp-blender
- Krita MCP: https://github.com/nanayax3/krita-mcp
