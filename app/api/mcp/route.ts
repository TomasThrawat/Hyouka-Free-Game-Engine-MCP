export const dynamic = "force-dynamic";
export const revalidate = 0;

import { createMcpHandler } from "mcp-handler";
import { fromJsonSchema } from "@modelcontextprotocol/server";
import type { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import {
  discoverRemoteMcpTools,
  gameCapabilityAudit,
  remoteMcpStatus,
  remoteMcpToolInventory,
  remoteMcpToolSchema,
  invokeRemoteMcpTool,
  refreshRemoteMcpCaches,
} from "../../../lib/remote-mcp";

const CONFIG =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/godot-bridge.json";

type BridgeTool = {
  id: string;
  description?: string;
};

let toolCache: { expiresAt: number; tools: BridgeTool[] } | null = null;

async function base() {
  if (process.env.GODOT_BRIDGE_URL) {
    return process.env.GODOT_BRIDGE_URL.replace(/\/$/, "");
  }

  try {
    const r = await fetch(CONFIG + "?t=" + Date.now(), {
      cache: "no-store",
      headers: { "cache-control": "no-cache", pragma: "no-cache" },
    });
    const x = await r.json();
    return x.status === "ok" && x.url
      ? String(x.url).replace(/\/$/, "")
      : null;
  } catch {
    return null;
  }
}

async function call(path: string, body?: unknown) {
  const b = await base();
  if (!b) {
    return { status: "not_configured", engine: "Godot", config: CONFIG };
  }

  try {
    const r = await fetch(b + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    const t = await r.text();
    let x: unknown;
    try {
      x = JSON.parse(t);
    } catch {
      x = { status: "error", message: t };
    }

    return r.ok
      ? x
      : {
          status: "error",
          httpStatus: r.status,
          ...(x && typeof x === "object" ? x : {}),
        };
  } catch (e) {
    return { status: "error", message: String(e) };
  }
}

async function discoverTools(): Promise<BridgeTool[]> {
  const now = Date.now();
  if (toolCache && toolCache.expiresAt > now) {
    return toolCache.tools;
  }

  const result = await call("/discover");
  const tools =
    result &&
    typeof result === "object" &&
    Array.isArray((result as { tools?: unknown }).tools)
      ? (result as { tools: unknown[] }).tools.filter(
          (tool): tool is BridgeTool =>
            !!tool &&
            typeof tool === "object" &&
            typeof (tool as { id?: unknown }).id === "string",
        )
      : [];

  toolCache = { expiresAt: now + 15_000, tools };
  return tools;
}

const common = z.object({
  args: z.array(z.string().max(4096)).max(128).default([]),
  cwd: z.string().max(2048).optional(),
  timeoutSeconds: z.number().int().min(1).max(600).optional(),
  background: z.boolean().optional(),
});

const out = (x: unknown) => {
  if (
    x &&
    typeof x === "object" &&
    Array.isArray((x as { content?: unknown }).content)
  ) {
    const raw = (x as { content: unknown[] }).content;
    const imageBlocks = raw.filter(
      (block): block is { type: "image"; data: string; mimeType: string } =>
        !!block &&
        typeof block === "object" &&
        (block as { type?: unknown }).type === "image" &&
        typeof (block as { data?: unknown }).data === "string" &&
        typeof (block as { mimeType?: unknown }).mimeType === "string",
    );
    if (imageBlocks.length > 0) {
      const metadata = { ...(x as Record<string, unknown>) };
      delete metadata.content;
      return {
        content: [
          ...imageBlocks,
          {
            type: "text" as const,
            text: JSON.stringify(metadata, null, 2),
          },
        ],
      };
    }
  }

  return {
    content: [{ type: "text" as const, text: JSON.stringify(x, null, 2) }],
  };
};

function uniqueToolName(id: string, used: Set<string>) {
  const normalized = ("godot_" + id.replace(/[^A-Za-z0-9_.-]/g, "_")).slice(
    0,
    120,
  );
  let name = normalized || "godot_tool";
  let suffix = 2;

  while (used.has(name)) {
    const tail = "_" + suffix++;
    name = (normalized || "godot_tool").slice(0, 128 - tail.length) + tail;
  }

  used.add(name);
  return name;
}

function registerIntegratedDccTools(
  server: McpServer,
  remoteTools: Awaited<ReturnType<typeof discoverRemoteMcpTools>>,
  used: Set<string>,
) {
  for (const tool of remoteTools) {
    const providerPrefix =
      tool.provider.id === "blender-dcc"
        ? "blender__"
        : tool.provider.id === "krita"
          ? "krita__"
          : null;

    if (!providerPrefix) continue;

    const name = uniqueToolName(providerPrefix + tool.name, used);
    const label = tool.provider.id === "blender-dcc" ? "Blender" : "Krita";

    server.registerTool(
      name,
      {
        title: "Godot / " + label + ": " + tool.name,
        description:
          tool.description ??
          "Native " +
            label +
            " capability exposed directly inside the unified Godot MCP.",
        inputSchema: fromJsonSchema(tool.inputSchema),
      },
      async (args) =>
        tool.client.callTool({
          name: tool.name,
          arguments: (args ?? {}) as Record<string, unknown>,
        }),
    );
  }
}

async function createHandler() {
  const [inventory, remoteTools] = await Promise.all([
    discoverTools(),
    discoverRemoteMcpTools(),
  ]);

  return createMcpHandler((server) => {
    const used = new Set<string>();

    server.registerTool(
      "godot_invoke_tool",
      {
        title: "Invoke any Godot tool",
        description:
          "Universal fallback for invoking any current Godot bridge tool by its discovered tool id.",
        inputSchema: z.object({
          toolId: z.string().min(1).max(256),
          ...common.shape,
        }),
      },
      async (args) => out(await call("/invoke", args)),
    );

    server.registerTool(
      "godot_discover_tools",
      {
        title: "Refresh Godot tool inventory",
        description:
          "Refresh and return the complete tool inventory exposed by the live Godot bridge.",
      },
      async () => {
        toolCache = null;
        return out(await call("/discover"));
      },
    );

    server.registerTool(
      "godot_status",
      {
        title: "Godot status",
        description: "Check the live Godot runtime.",
      },
      async () => out(await call("/health")),
    );

    server.registerTool(
      "godot_remote_providers",
      {
        title: "Godot integrated provider status",
        description:
          "Show Blender and Krita integration status inside the unified Godot MCP.",
        inputSchema: z.object({}),
      },
      async () => {
        const status = await remoteMcpStatus();
        return out({
          providers: status.providers.filter(
            (provider) =>
              provider.id === "blender-dcc" || provider.id === "krita",
          ),
        });
      },
    );

    server.registerTool(
      "godot_game_capability_audit",
      {
        title: "Full Godot game capability audit",
        description:
          "Return the free-game capability matrix and the status of integrated Blender and Krita capabilities.",
        inputSchema: z.object({}),
      },
      async () => out(await gameCapabilityAudit()),
    );

    server.registerTool(
      "godot_refresh_integrated_tools",
      {
        title: "Refresh integrated Godot tools",
        description:
          "Refresh the Godot, Blender, and Krita tool inventories exposed by this one unified MCP.",
        inputSchema: z.object({}),
      },
      async () => {
        refreshRemoteMcpCaches();
        toolCache = null;
        return out({
          godot: await call("/discover"),
          integrated: await remoteMcpToolInventory(),
        });
      },
    );

    for (const tool of inventory) {
      const name = uniqueToolName(tool.id, used);
      server.registerTool(
        name,
        {
          title: "Godot: " + tool.id,
          description:
            tool.description ||
            ("Invoke the discovered Godot tool " +
              JSON.stringify(tool.id) +
              " with its CLI-style arguments."),
          inputSchema: common,
        },
        async (args) =>
          out(await call("/invoke", { ...args, toolId: tool.id })),
      );
    }

    registerIntegratedDccTools(server, remoteTools, used);
  });
}

async function handler(req: Request) {
  const mcp = await createHandler();
  return mcp(req);
}

export { handler as GET, handler as POST };
