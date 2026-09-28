# Hyouka Free Game Engine MCP

No-PC, free-only game-engine MCP stack.

## Architecture

Android / ChatGPT
-> Composio
-> Vercel Streamable HTTP MCP
-> GitHub Actions standard public runner
-> headless Blender
-> Cloudflare Quick Tunnel
-> Blender HTTP bridge

The Vercel MCP reads `runtime/blender-bridge.json` dynamically, so the Cloudflare URL can rotate without changing the Composio MCP endpoint.

## Free Blender Runtime

The repository uses a standard `ubuntu-latest` GitHub-hosted runner in a public repository.

The Blender runtime is designed as a self-renewing service:
1. Blender runs headlessly on the GitHub runner.
2. Cloudflare Quick Tunnel exposes port 9765.
3. The live tunnel URL is published to `runtime/blender-bridge.json`.
4. A supervisor runs every 5 minutes.
5. When there is no runtime it starts one.
6. When a runtime is close to the job limit it starts a replacement before the old one ends.
7. Runtime concurrency allows the old and replacement runtimes to overlap, so the newest heartbeat URL becomes active before the previous runner disappears.

Each individual GitHub VM and Quick Tunnel is temporary. The supervisor is what makes the overall runtime continuously renew itself. GitHub scheduling or Cloudflare availability can still cause an outage, so this is a free development/testing service rather than a contractual 24/7 SLA.

## Blender MCP Tools

- blender_status
- blender_new_scene
- blender_create_basic_scene
- blender_list_objects
- blender_add_primitive
- blender_transform_object
- blender_delete_object
- blender_save_blend
- blender_render
- blender_export_glb

The bridge does not expose arbitrary remote Python execution.

## Browser-native editors

- Godot Web Editor: https://editor.godotengine.org/
- GDevelop: https://editor.gdevelop.io/
- Construct 3: https://editor.construct.net/

## Free-only boundaries

This repository does not depend on:
- paid GPU cloud
- paid AI APIs
- paid Vercel plans
- paid Cloudflare tunnels
- paid GitHub Actions overage
- Unity/Unreal cloud runtimes

The GitHub runner model used here is the standard runner for a public repository.
