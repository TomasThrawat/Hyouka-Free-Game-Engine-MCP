import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";

const DEFAULT_BRIDGE_CONFIG_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/o3de-bridge.json";

const O3DE_COMMANDS = [
  ["get-global-project", "Read or manage the configured global project. Pass the exact O3DE CLI arguments in args."],
  ["set-global-project", "Set the configured global project. Pass the exact O3DE CLI arguments in args."],
  ["create-template", "Create an O3DE engine template. Pass the exact O3DE CLI arguments in args."],
  ["create-from-template", "Create an engine from a template. Pass the exact O3DE CLI arguments in args."],
  ["register", "Register an O3DE engine, project, gem, or repository path. Pass the exact O3DE CLI arguments in args."],
  ["register-show", "Print the current O3DE registration database. Pass the exact O3DE CLI arguments in args."],
  ["get-registered", "Get a registered O3DE object by name or path. Pass the exact O3DE CLI arguments in args."],
  ["enable-gem", "Enable an O3DE Gem for a project. Pass the exact O3DE CLI arguments in args."],
  ["disable-gem", "Disable an O3DE Gem for a project. Pass the exact O3DE CLI arguments in args."],
  ["edit-engine-properties", "Read or edit O3DE engine properties. Pass the exact O3DE CLI arguments in args."],
  ["edit-project-properties", "Read or edit O3DE project properties. Pass the exact O3DE CLI arguments in args."],
  ["edit-gem-properties", "Read or edit O3DE Gem properties. Pass the exact O3DE CLI arguments in args."],
  ["sha256", "Calculate SHA-256 values using the O3DE CLI. Pass the exact O3DE CLI arguments in args."],
  ["download", "Use the O3DE downloader. Pass the exact O3DE CLI arguments in args."],
  ["export-project-configure", "Configure O3DE project export defaults. Pass the exact O3DE CLI arguments in args."],
  ["export-project", "Export an O3DE project. Pass the exact O3DE CLI arguments in args."],
  ["repo", "Create or manage an O3DE repository. Pass the exact O3DE CLI arguments in args."],
  ["edit-repo-properties", "Read or edit O3DE repository properties. Pass the exact O3DE CLI arguments in args."],
] as const;

type BridgeResult = Record<string, unknown>;

function trimUrl(value: unknown) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/\/$/, "");
  return /^https:\/\//.test(trimmed) ? trimmed : null;
}

async function resolveBridgeUrl() {
  const configUrl =
    process.env.O3DE_BRIDGE_CONFIG_URL?.trim() || DEFAULT_BRIDGE_CONFIG_URL;

  try {
    const response = await fetch(
      `${configUrl}${configUrl.includes("?") ? "&" : "?"}t=${Date.now()}`,
      { cache: "no-store" },
    );
    if (response.ok) {
      const payload = (await response.json()) as { url?: unknown; status?: unknown };
      if (payload.status === "ok") {
        const dynamicUrl = trimUrl(payload.url);
        if (dynamicUrl) return dynamicUrl;
      }
    }
  } catch {
    // Fall through to an explicitly configured direct URL.
  }

  return trimUrl(process.env.O3DE_BRIDGE_URL);
}

async function callO3DE(
  path: string,
  body?: Record<string, unknown>,
): Promise<BridgeResult> {
  const base = await resolveBridgeUrl();

  if (!base) {
    return {
      status: "not_configured",
      error: "No live O3DE bridge URL is configured.",
      expected: "O3DE_BRIDGE_URL or a runtime/o3de-bridge.json file with status=ok.",
      hint:
        "The Vercel MCP is deployed, but O3DE itself must run on a separate Linux/Windows host or Codespace.",
    };
  }

  try {
    const response = await fetch(base + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
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
      return { status: "error", ...payload, httpStatus: response.status };
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

const cliInput = z.object({
  args: z.array(z.string().max(512)).max(64).default([]),
  cwd: z.string().max(1024).optional(),
  timeoutSeconds: z.number().int().min(1).max(300).optional(),
});

const handler = createMcpHandler((server) => {
  server.registerTool(
    "o3de_status",
    {
      title: "O3DE Status",
      description:
        "Check whether the remote O3DE bridge is reachable and which O3DE installation it exposes.",
    },
    async () => textResult(await callO3DE("/health")),
  );

  server.registerTool(
    "o3de_commands",
    {
      title: "O3DE Commands",
      description:
        "List every first-party CLI subcommand wired by the O3DE scripts/o3de.py entry point in the inspected O3DE source tree.",
    },
    async () =>
      textResult({
        engine: "Open 3D Engine (O3DE)",
        sourceRepository: "https://github.com/o3de/o3de",
        sourceRef: "development",
        sourceEntryPoint: "scripts/o3de.py",
        commands: O3DE_COMMANDS.map(([command, description]) => ({
          command,
          description,
          mcpTool: `o3de_${command.replace(/-/g, "_")}`,
        })),
        note:
          "android.py is imported by o3de.py but does not register a top-level argparse subcommand in the inspected source, so it is not exposed as a separate CLI tool.",
      }),
  );

  server.registerTool(
    "o3de_cli_help",
    {
      title: "O3DE CLI Help",
      description:
        "Ask the actual O3DE scripts/o3de.py entry point for its current CLI help output.",
      inputSchema: z.object({
        topic: z.string().max(120).optional(),
      }),
    },
    async ({ topic }) =>
      textResult(
        await callO3DE("/help", {
          topic: topic?.trim() || "",
        }),
      ),
  );

  for (const [command, description] of O3DE_COMMANDS) {
    const toolName = `o3de_${command.replace(/-/g, "_")}`;
    server.registerTool(
      toolName,
      {
        title: `O3DE ${command}`,
        description: `${description} The bridge executes argv directly and never invokes a shell.`,
        inputSchema: cliInput,
      },
      async ({ args, cwd, timeoutSeconds }) =>
        textResult(
          await callO3DE("/cli", {
            command,
            args,
            cwd,
            timeoutSeconds,
          }),
        ),
    );
  }
});

export { handler as GET, handler as POST };
