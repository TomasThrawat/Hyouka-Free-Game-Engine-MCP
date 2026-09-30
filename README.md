# Hyouka Game Engine MCP

Vercel Streamable HTTP MCP gateway for the free game-engine stack.

## Main providers

- Godot: game engine, project/build/runtime control.
- Blender: 3D modeling, scenes, meshes, materials, animation, rendering, and GLB export.
- Krita: 2D canvas, layers, painting, shapes, filters, export, and texture-source artwork.

## Dedicated Vercel HTTP MCP endpoints

The project now exposes provider-specific Streamable HTTP MCP endpoints:

- `/api/mcp/blender` -> Blender DCC MCP provider.
- `/api/mcp/krita` -> Krita MCP provider.

The Vercel layer is the HTTP MCP server. Blender and Krita themselves still run in the DCC runtime/Codespace; Vercel forwards MCP tool calls to the live provider over HTTP. Vercel does not run the Blender or Krita desktop binaries.

Both endpoints require the Vercel environment variable `HYOUKA_DCC_HTTP_MCP_TOKEN` and a matching `Authorization: Bearer <token>` header. Upstream provider credentials remain server-side and are never forwarded to the MCP client.

Vercel supports MCP servers through `mcp-handler` and Streamable HTTP. See the Vercel MCP documentation for the current deployment model.
