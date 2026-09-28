export function GET() {
  return Response.json({
    name: "hyouka-free-game-engine-mcp",
    status: "ok",
    mcpEndpoint: "/api/mcp",
    policy: "free-only-no-pc",
    browserEngines: ["godot-web", "gdevelop-web", "construct-web"],
    blender: {
      mode: "headless-codespaces",
      configured: Boolean(process.env.BLENDER_BRIDGE_URL),
      bridgePort: 9765,
    },
    desktopEditors: ["unity", "unreal"],
    desktopRuntimeStatus: "not-provisioned",
  });
}
