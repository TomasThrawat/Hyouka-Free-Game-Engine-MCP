const bridgeConfigUrl =
  process.env.BLENDER_BRIDGE_CONFIG_URL ||
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/blender-bridge.json";

export function GET() {
  return Response.json({
    name: "hyouka-free-game-engine-mcp",
    status: "ok",
    mcpEndpoint: "/api/mcp",
    policy: "free-only-no-pc",
    browserEngines: ["godot-web", "gdevelop-web", "construct-web"],
    blender: {
      mode: "headless-codespaces",
      bridgeConfigUrl,
      directBridgeConfigured: Boolean(process.env.BLENDER_BRIDGE_URL),
      port: 9765,
      tunnel: "Cloudflare Quick Tunnel",
    },
    desktopEditors: ["unity", "unreal"],
    desktopRuntimeStatus: "not-provisioned",
  });
}
