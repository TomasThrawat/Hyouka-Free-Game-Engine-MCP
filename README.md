# Hyouka Free Game Engine MCP

No-PC, free-first game-engine MCP stack.

## Architecture

Android browser / ChatGPT
-> Composio
-> Vercel Streamable HTTP MCP
-> GitHub Codespaces
-> headless Blender bridge

Browser-native editors remain available:
- Godot Web Editor: https://editor.godotengine.org/
- GDevelop: https://editor.gdevelop.io/
- Construct 3: https://editor.construct.net/

## Blender backend

This repository now includes a minimal dependency-free Blender HTTP bridge in `blender/server.py`.

It runs inside Blender headless mode and exposes:
- `/health`
- scene reset and basic-scene creation
- object list/add/transform/delete
- `.blend` save
- CPU/Eevee PNG render
- GLB export
- artifact download under `/files/<name>`

The public MCP surface is:
`https://hyouka-free-game-engine-mcp.vercel.app/api/mcp`

New Blender MCP tools:
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

## Codespaces

The devcontainer installs Blender from the Debian package and starts the bridge on port `9765`.

GitHub Codespaces public forwarding uses:
`https://CODESPACENAME-9765.app.github.dev`

The Vercel deployment reads:
`BLENDER_BRIDGE_URL`

Set that variable to the public Codespaces bridge URL. No paid GPU service is required.

## Free-only policy

This project does not rely on:
- paid GPU cloud desktops
- paid overage
- paid AI APIs
- Unity cloud editor runtime
- Unreal cloud editor runtime

GitHub Codespaces availability and quota are controlled by GitHub's current free plan. When the free quota is exhausted, do not enable paid overage.

## Scope

Blender is the desktop-grade 3D engine backend; browser engines are the no-install alternatives.
