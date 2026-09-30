import { createMcpHandler } from "mcp-handler";
import {
  discoverRemoteMcpTools,
  registerRemoteMcpTools,
  type RemoteMcpTool,
} from "./remote-mcp";

const GATEWAY_TOKEN_ENV = "HYOUKA_DCC_HTTP_MCP_TOKEN";

export async function createDccHttpMcpHandler(providerId: string) {
  const handler = createMcpHandler(
    async (server) => {
      const tools = await discoverRemoteMcpTools();
      const providerTools = tools.filter(
        (tool: RemoteMcpTool) => tool.provider.id === providerId,
      );

      if (providerTools.length === 0) {
        throw new Error(
          `DCC provider "${providerId}" is unavailable or has no discovered tools.`,
        );
      }

      const usedNames = new Set<string>();
      registerRemoteMcpTools(server, providerTools, usedNames);
    },
    {
      serverInfo: {
        name: `hyouka-${providerId}-http-mcp`,
        version: "1.0.0",
      },
    },
  );

  return async (request: Request) => {
    const expected = process.env[GATEWAY_TOKEN_ENV]?.trim();

    if (!expected) {
      return Response.json(
        {
          error: "not_configured",
          message: `${GATEWAY_TOKEN_ENV} is required for the public DCC MCP endpoint.`,
        },
        { status: 503 },
      );
    }

    const authorization = request.headers.get("authorization") ?? "";
    const supplied = authorization.startsWith("Bearer ")
      ? authorization.slice("Bearer ".length).trim()
      : "";

    if (!supplied || supplied !== expected) {
      return new Response(JSON.stringify({ error: "unauthorized" }), {
        status: 401,
        headers: {
          "content-type": "application/json",
          "www-authenticate": "Bearer",
        },
      });
    }

    return handler(request);
  };
}
