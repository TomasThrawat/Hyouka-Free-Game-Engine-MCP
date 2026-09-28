import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";

const DEFAULT_BRIDGE_CONFIG_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/o3de-bridge.json";

const O3DE_COMMANDS = [
  "get-global-project",
  "set-global-project",
  "create-template",
  "create-from-template",
  "register",
  "register-show",
  "get-registered",
  "enable-gem",
  "disable-gem",
  "edit-engine-properties",
  "edit-project-properties",
  "edit-gem-properties",
  "sha256",
  "download",
  "export-project-configure",
  "export-project",
  "repo",
  "edit-repo-properties",
] as const;

type BridgeResult = Record<string, unknown>;

function trimUrl(value: unknown) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/\/$/, "");
  return /^https:\/\//.test(trimmed) ? trimmed : null;
}

async function resolveBridge() {
  const configUrl =
    process.env.O3DE_BRIDGE_CONFIG_URL?.trim() || DEFAULT_BRIDGE_CONFIG_URL;

  try {
    const response = await fetch(
      `${configUrl}${configUrl.includes("?") ? "&" : "?"}t=${Date.now()}`,
      { cache: "no-store" },
    );

    if (response.ok) {
      const payload = (await response.json()) as {
        status?: unknown;
        url?: unknown;
      };

      if (payload.status === "ok") {
        const url = trimUrl(payload.url);
        if (url) return url;
      }
    }
  } catch {
    // Fall through to direct configuration.
  }

  return trimUrl(process.env.O3DE_BRIDGE_URL);
}

async function callBridge(
  path: string,
  body?: Record<string, unknown>,
): Promise<BridgeResult> {
  const bridgeUrl = await resolveBridge();

  if (!bridgeUrl) {
    return {
      status: "not_configured",
      error: "No live O3DE bridge URL is configured.",
      expected:
        "O3DE_BRIDGE_URL or runtime/o3de-bridge.json with status=ok and an HTTPS url.",
      hint:
        "The Vercel MCP layer is live. O3DE execution requires a separate bridge host with O3DE installed.",
    };
  }

  const headers: Record<string, string> = {};
  const token = process.env.O3DE_BRIDGE_TOKEN?.trim();

  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["content-type"] = "application/json";

  try {
    const response = await fetch(bridgeUrl + path, {
      method: body ? "POST" : "GET",
      headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });

    const raw = await response.text();

    let payload: BridgeResult;
    try {
      payload = JSON.parse(raw) as BridgeResult;
    } catch {
      payload = { status: "error", message: raw };
    }

    if (!response.ok) {
      return {
        status: "error",
        ...payload,
        httpStatus: response.status,
      };
    }

    return payload;
  } catch (error) {
    return {
      status: "error",
      error: "bridge_request_failed",
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

const textResult = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }],
});

const commonInput = z.object({
  args: z.array(z.string().max(4096)).max(128).default([]),
  cwd: z.string().max(2048).optional(),
  timeoutSeconds: z.number().int().min(1).max(600).optional(),
  background: z.boolean().optional(),
});

const handler = createMcpHandler((server) => {
  server.registerTool(
    "o3de_status",
    {
      title: "O3DE Status",
      description:
        "Check the live O3DE bridge and report its discovered tool counts and engine/build paths.",
    },
    async () => textResult(await callBridge("/health")),
  );

  server.registerTool(
    "o3de_discover_tools",
    {
      title: "Discover All O3DE Tools",
      description:
        "Dynamically inventory callable O3DE Python scripts, shell scripts, built executables, first-party CLI commands, CMake targets, and CTest registrations.",
      inputSchema: z.object({
        maxTools: z.number().int().min(1).max(2000).optional(),
        probeHelp: z.boolean().optional(),
      }),
    },
    async ({ maxTools, probeHelp }) => {
      const result = await callBridge("/discover");
      if (result.status !== "ok") return textResult(result);

      const tools = Array.isArray(result.tools)
        ? result.tools.slice(0, maxTools ?? 2000)
        : [];

      if (!probeHelp) {
        return textResult({
          ...result,
          tools,
          returnedTools: tools.length,
        });
      }

      const probes = [];
      for (const tool of tools.slice(0, 25)) {
        const id = (tool as { id?: unknown }).id;
        if (typeof id === "string") {
          probes.push(await callBridge("/probe", { toolId: id }));
        }
      }

      return textResult({
        ...result,
        tools,
        probes,
        returnedTools: tools.length,
        probedTools: Math.min(tools.length, 25),
      });
    },
  );

  server.registerTool(
    "o3de_find_tools",
    {
      title: "Find O3DE Tools",
      description:
        "Search the dynamic O3DE inventory by id, name, path, kind, or source without returning the full inventory.",
      inputSchema: z.object({
        query: z.string().max(200).optional(),
        kind: z.string().max(80).optional(),
        callableOnly: z.boolean().optional(),
      }),
    },
    async ({ query, kind, callableOnly }) => {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (kind) params.set("kind", kind);
      params.set("callable", String(callableOnly !== false));

      return textResult(await callBridge(`/find?${params.toString()}`));
    },
  );

  server.registerTool(
    "o3de_probe_tool",
    {
      title: "Probe O3DE Tool",
      description:
        "Run --help against one discovered O3DE executable/script/CLI tool and return its actual help output.",
      inputSchema: z.object({
        toolId: z.string().min(1).max(4096),
      }),
    },
    async ({ toolId }) => textResult(await callBridge("/probe", { toolId })),
  );

  server.registerTool(
    "o3de_invoke_tool",
    {
      title: "Invoke Any O3DE Tool",
      description:
        "Universal O3DE dispatcher for every callable tool_id returned by discovery, including Python, shell scripts, built executables, CLI commands, CMake targets, and CTest registrations.",
      inputSchema: z.object({
        toolId: z.string().min(1).max(4096),
        ...commonInput.shape,
      }),
    },
    async ({ toolId, args, cwd, timeoutSeconds, background }) =>
      textResult(
        await callBridge("/invoke", {
          toolId,
          args,
          cwd,
          timeoutSeconds,
          background,
        }),
      ),
  );

  server.registerTool(
    "o3de_build_target",
    {
      title: "Build Any O3DE Target",
      description:
        "Build a configured O3DE CMake target with optional configuration, parallel jobs, timeout, and background execution.",
      inputSchema: z.object({
        target: z.string().min(1).max(512),
        config: z.string().max(100).optional(),
        jobs: z.number().int().min(0).max(32).optional(),
        cwd: z.string().max(2048).optional(),
        timeoutSeconds: z.number().int().min(1).max(600).optional(),
        background: z.boolean().optional(),
      }),
    },
    async ({ target, config, jobs, cwd, timeoutSeconds, background }) =>
      textResult(
        await callBridge("/build", {
          target,
          config,
          jobs,
          cwd,
          timeoutSeconds,
          background,
        }),
      ),
  );

  server.registerTool(
    "o3de_processes",
    {
      title: "O3DE Processes",
      description:
        "List bridge-managed background O3DE/tool processes.",
    },
    async () => textResult(await callBridge("/processes")),
  );

  server.registerTool(
    "o3de_stop_process",
    {
      title: "Stop O3DE Process",
      description:
        "Stop a background process previously started through the bridge.",
      inputSchema: z.object({
        pid: z.number().int().positive(),
      }),
    },
    async ({ pid }) => textResult(await callBridge("/stop", { pid })),
  );

  server.registerTool(
    "o3de_cli",
    {
      title: "O3DE CLI",
      description:
        "Compatibility wrapper for any top-level command dynamically found in scripts/o3de.py.",
      inputSchema: z.object({
        command: z.string().min(1).max(200),
        ...commonInput.shape,
      }),
    },
    async ({ command, args, cwd, timeoutSeconds, background }) =>
      textResult(
        await callBridge("/cli", {
          command,
          args,
          cwd,
          timeoutSeconds,
          background,
        }),
      ),
  );

  server.registerTool(
    "o3de_cli_help",
    {
      title: "O3DE CLI Help",
      description:
        "Ask scripts/o3de.py for its current CLI help output.",
      inputSchema: z.object({
        topic: z.string().max(120).optional(),
      }),
    },
    async ({ topic }) =>
      textResult(await callBridge("/help", { topic: topic?.trim() || "" })),
  );

  for (const command of O3DE_COMMANDS) {
    const toolName = `o3de_${command.replace(/-/g, "_")}`;

    server.registerTool(
      toolName,
      {
        title: `O3DE ${command}`,
        description:
          "Compatibility shortcut for a first-party O3DE top-level command. Use o3de_invoke_tool for all dynamically discovered non-top-level tools.",
        inputSchema: commonInput,
      },
      async ({ args, cwd, timeoutSeconds, background }) =>
        textResult(
          await callBridge("/cli", {
            command,
            args,
            cwd,
            timeoutSeconds,
            background,
          }),
        ),
    );
  }
});

export { handler as GET, handler as POST };
