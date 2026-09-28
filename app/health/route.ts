export function GET() {
  return Response.json({
    name:"hyouka-free-game-engine-mcp",
    status:"ok",
    mcpEndpoint:"/api/mcp",
    policy:"free-only-no-pc",
    browserEngines:["godot-web","gdevelop-web","construct-web"],
    desktopEditors:["unity","unreal"],
    desktopRuntimeStatus:"not-provisioned"
  });
}
