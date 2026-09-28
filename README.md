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

Browser-native editors remain available:
- Godot Web Editor: https://editor.godotengine.org/
- GDevelop: https://editor.gdevelop.io/
- Construct 3: https://editor.construct.net/

## Free Blender runtime

The repository runs Blender headlessly on a standard GitHub-hosted runner in a public repository. GitHub currently documents standard runners for public repositories as free and unlimited. The runtime job is intentionally capped below GitHub's six-hour hosted-job limit and uses a normal `ubuntu-latest` runner, not a larger billed runner.

The workflow starts:
1. Blender headless on port 9765.
2. A Cloudflare Quick Tunnel exposing the HTTP bridge.
3. A public runtime heartbeat file at `runtime/blender-bridge.json`.

The Vercel MCP reads that heartbeat file dynamically, so the live tunnel URL is discovered without manually editing Vercel configuration.

Cloudflare Quick Tunnels are free, require no Cloudflare account, generate a random `trycloudflare.com` URL, and are intended for development/testing. They have a 200 in-flight request limit and do not support SSE. This Blender bridge is plain HTTP JSON, so the SSE limitation does not apply to it.

## Blender MCP tools

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

The bridge intentionally does not expose arbitrary remote Python execution.

## Free-only boundaries

This repository does not depend on:
- paid GPU cloud
- paid AI APIs
- Vercel paid plan
- Cloudflare paid tunnels
- GitHub Actions paid overage
- Unity/Unreal cloud editor runtime

The GitHub repository is public, so standard GitHub-hosted Actions runners are free. The workflow uses the standard runner only. GitHub documents that standard runners in public repositories are free and unlimited, while larger runners are billed.

The runtime is temporary: GitHub-hosted workflow jobs have a finite maximum duration, and Cloudflare Quick Tunnels have no uptime/SLA guarantee. The system is therefore a free development/testing runtime, not a persistent production server.
