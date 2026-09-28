# Hyouka Free Game Engine MCP

No-PC, free-only game-engine MCP stack.

## Architecture

Android / ChatGPT
-> Composio
-> Vercel Streamable HTTP MCP
-> GitHub Codespaces
-> headless Blender
-> Cloudflare Quick Tunnel
-> Blender HTTP bridge

Browser-native editors remain available:
- Godot Web Editor: https://editor.godotengine.org/
- GDevelop: https://editor.gdevelop.io/
- Construct 3: https://editor.construct.net/

## Blender backend

The repository includes a minimal Blender HTTP bridge in `blender/server.py`.

Supported operations:
- health check
- clear scene
- create a basic game-style scene
- list objects
- add / transform / delete primitives
- save `.blend`
- CPU/Eevee PNG render
- GLB export
- artifact download

## Fully-free remote access

GitHub Codespaces runs Blender headlessly on CPU.

GitHub port forwarding is not used for the Blender bridge. Instead, the Codespace starts a Cloudflare Quick Tunnel:
`cloudflared tunnel --url http://127.0.0.1:9765`

Cloudflare documents Quick Tunnels as free, temporary, no-account tunnels that generate a random `trycloudflare.com` URL. They are intended for development/testing and have a 200 in-flight request limit; they also do not support SSE. The Blender bridge is plain HTTP, so the SSE limitation does not affect the bridge transport. See https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/

On every Codespace start, the tunnel URL is written to:
`runtime/blender-bridge.json`

The Vercel MCP reads that public GitHub JSON dynamically, so no manual URL update is required after a Codespace restart.

## MCP tools

- `blender_status`
- `blender_new_scene`
- `blender_create_basic_scene`
- `blender_list_objects`
- `blender_add_primitive`
- `blender_transform_object`
- `blender_delete_object`
- `blender_save_blend`
- `blender_render`
- `blender_export_glb`

## Free-only policy

No paid GPU cloud.
No paid AI API.
No Vercel paid plan.
No Cloudflare account or paid tunnel.
No paid Codespaces overage.
No Unity/Unreal cloud editor runtime.

GitHub Codespaces has a free quota; when it is exhausted, usage must stop rather than using paid overage.

## Important

Quick Tunnels are temporary and have no uptime guarantee. They are a development/testing transport, not a production SLA.

The Blender bridge intentionally exposes only constrained scene operations and does not expose arbitrary remote Python execution.
