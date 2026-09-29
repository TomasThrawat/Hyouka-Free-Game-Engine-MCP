export const dynamic = "force-dynamic";
export const revalidate = 0;

import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";
import {
  discoverRemoteMcpTools,
  gameCapabilityAudit,
  registerRemoteMcpTools,
  remoteMcpStatus,
} from "../../../lib/remote-mcp";

const CONFIG =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/godot-bridge.json";

type BridgeTool = {
  id: string;
  kind?: string;
  callable?: boolean;
  flag?: string;
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

function toolName(id: string, used: Set<string>) {
  const baseName = ("godot_" + id.replace(/[^A-Za-z0-9_.-]/g, "_")).slice(0, 120);
  let name = baseName || "godot_tool";
  let suffix = 2;

  while (used.has(name)) {
    const tail = "_" + suffix++;
    name =
      (baseName || "godot_tool").slice(0, 128 - tail.length) + tail;
  }

  used.add(name);
  return name;
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
      "mcp_remote_providers",
      {
        title: "Remote MCP provider status",
        description:
          "Show configured remote MCP providers, their source projects, connection state, and discovered tool counts.",
        inputSchema: z.object({}),
      },
      async () => out(await remoteMcpStatus()),
    );

    server.registerTool(
      "game_capability_audit",
      {
        title: "Full game capability audit",
        description:
          "Return the free-game production capability matrix plus live remote provider configuration, connection state, and discovered tool counts.",
        inputSchema: z.object({}),
      },
      async () => out(await gameCapabilityAudit()),
    );

    for (const tool of inventory) {
      const name = toolName(tool.id, used);
      const description =
        tool.description ||
        ("Invoke the discovered Godot tool " +
          JSON.stringify(tool.id) +
          " with its CLI-style arguments.");

      server.registerTool(
        name,
        {
          title: "Godot: " + tool.id,
          description,
          inputSchema: common,
        },
        async (args) =>
          out(await call("/invoke", { ...args, toolId: tool.id })),
      );
    }

    registerRemoteMcpTools(server, remoteTools, used);
  });
}

async function handler(req: Request) {
  const mcp = await createHandler();
  return mcp(req);
}

export { handler as GET, handler as POST };
