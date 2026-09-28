const DEFAULT_BRIDGE_CONFIG_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/o3de-bridge.json";

function validHttpsUrl(value: unknown) {
  if (typeof value !== "string") return null;
  const url = value.trim();
  return /^https:\/\//.test(url) ? url.replace(/\/$/, "") : null;
}

async function fetchJson(url: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });

    const raw = await response.text();

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        payload: { status: "error", message: raw },
      };
    }

    try {
      return {
        ok: true,
        status: response.status,
        payload: JSON.parse(raw) as Record<string, unknown>,
      };
    } catch {
      return {
        ok: false,
        status: response.status,
        payload: { status: "error", message: raw },
      };
    }
  } finally {
    clearTimeout(timer);
  }
}

async function resolveBridge() {
  const direct = validHttpsUrl(process.env.O3DE_BRIDGE_URL);
  if (direct) {
    return { url: direct, source: "O3DE_BRIDGE_URL" };
  }

  const configUrl =
    process.env.O3DE_BRIDGE_CONFIG_URL || DEFAULT_BRIDGE_CONFIG_URL;

  try {
    const result = await fetchJson(
      `${configUrl}${configUrl.includes("?") ? "&" : "?"}t=${Date.now()}`,
    );

    if (result.ok && result.payload.status === "ok") {
      const manifestUrl = validHttpsUrl(result.payload.url);
      if (manifestUrl) {
        return { url: manifestUrl, source: "runtime/o3de-bridge.json" };
      }
    }
  } catch {
    // The manifest is optional until a live runtime is started.
  }

  return null;
}

export async function GET() {
  const bridge = await resolveBridge();

  let bridgeHealth: Record<string, unknown> | null = null;
  let bridgeSelftest: Record<string, unknown> | null = null;

  if (bridge) {
    try {
      const healthResult = await fetchJson(`${bridge.url}/health`);
      bridgeHealth = {
        httpStatus: healthResult.status,
        ...(healthResult.payload || {}),
      };

      const selftestResult = await fetchJson(`${bridge.url}/selftest`);
      bridgeSelftest = {
        httpStatus: selftestResult.status,
        ...(selftestResult.payload || {}),
      };
    } catch (error) {
      bridgeHealth = {
        status: "error",
        error: "bridge_probe_failed",
        message: error instanceof Error ? error.message : String(error),
      };
    }
  }

  const bridgeReady =
    bridgeHealth?.status === "ok" &&
    bridgeSelftest?.status === "ok";

  return Response.json({
    name: "hyouka-free-game-engine-mcp",
    status: "ok",
    mcpEndpoint: "/api/mcp",
    engine: "O3DE",
    source: "https://github.com/o3de/o3de",
    cliEntryPoint: "scripts/o3de.py",
    gatewayMode: "dynamic-callable-tool-discovery",
    bridgeConfigured: Boolean(bridge),
    directBridgeConfigured: Boolean(bridge),
    bridgeSource: bridge?.source || null,
    bridgeUrl: bridge?.url || null,
    bridgeReady,
    bridgeHealth,
    bridgeSelftest,
    bridgeConfigUrl:
      process.env.O3DE_BRIDGE_CONFIG_URL || DEFAULT_BRIDGE_CONFIG_URL,
    executionModel:
      "Vercel hosts MCP; O3DE commands execute through a separate universal HTTP bridge.",
  });
}
