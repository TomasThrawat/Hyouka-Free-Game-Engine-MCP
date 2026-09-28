const DEFAULT_BRIDGE_CONFIG_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/o3de-bridge.json";

export function GET() {
  return Response.json({
    name: "hyouka-free-game-engine-mcp",
    status: "ok",
    mcpEndpoint: "/api/mcp",
    engine: "O3DE",
    source: "https://github.com/o3de/o3de",
    cliEntryPoint: "scripts/o3de.py",
    gatewayMode: "dynamic-callable-tool-discovery",
    bridgeConfigUrl:
      process.env.O3DE_BRIDGE_CONFIG_URL || DEFAULT_BRIDGE_CONFIG_URL,
    directBridgeConfigured: Boolean(process.env.O3DE_BRIDGE_URL),
    executionModel:
      "Vercel hosts MCP; O3DE commands execute through a separate universal HTTP bridge.",
  });
}
