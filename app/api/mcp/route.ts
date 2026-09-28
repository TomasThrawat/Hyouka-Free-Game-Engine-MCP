import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";

const engines = {
  godot: {
    name: "Godot Web Editor",
    url: "https://editor.godotengine.org/",
    mode: "web",
  },
  gdevelop: {
    name: "GDevelop Web Editor",
    url: "https://editor.gdevelop.io/",
    mode: "web",
  },
  construct: {
    name: "Construct 3",
    url: "https://editor.construct.net/",
    mode: "web",
  },
} as const;

const DEFAULT_BRIDGE_CONFIG_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/blender-bridge.json";

type BridgeResult = {
  status?: string;
  error?: string;
  message?: string;
  [key: string]: unknown;
};

function trimUrl(value: unknown) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/\/$/, "");
  return /^https:\/\//.test(trimmed) ? trimmed : null;
}

async function resolveBridgeUrl() {
  const configUrl =
    process.env.BLENDER_BRIDGE_CONFIG_URL?.trim() || DEFAULT_BRIDGE_CONFIG_URL;

  try {
    const response = await fetch(
      `${configUrl}${configUrl.includes("?") ? "&" : "?"}t=${Date.now()}`,
      { cache: "no-store" },
    );
    if (response.ok) {
      const payload = (await response.json()) as { url?: unknown };
      const dynamicUrl = trimUrl(payload.url);
      if (dynamicUrl) return dynamicUrl;
    }
  } catch {
    // Fall back to a direct URL if a static URL was explicitly configured.
  }

  return trimUrl(process.env.BLENDER_BRIDGE_URL);
}

async function callBlender(
  path: string,
  body?: Record<string, unknown>,
): Promise<BridgeResult> {
  const base = await resolveBridgeUrl();

  if (!base) {
    return {
      status: "not_configured",
      error: "No live Blender bridge URL is available.",
      hint:
        "The free Codespaces runtime must be started so its Cloudflare Quick Tunnel URL can be published to GitHub.",
    };
  }

  try {
    const response = await fetch(base + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });

    const text = await response.text();
    let payload: BridgeResult;
    try {
      payload = JSON.parse(text) as BridgeResult;
    } catch {
      payload = { status: "error", message: text };
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

const artifactUrlFor = async (filename: unknown) => {
  const name = typeof filename === "string" ? filename : null;
  const base = await resolveBridgeUrl();
  return name && base ? `${base}/files/${encodeURIComponent(name)}` : undefined;
};

const handler = createMcpHandler((server) => {
  server.registerTool(
    "list_free_web_engines",
    {
      title: "List Free Web Engines",
      description:
        "List browser-native game engines available in the free no-PC stack.",
    },
    async () =>
      textResult({
        policy: "free-only-no-pc",
        engines: Object.entries(engines).map(([id, value]) => ({
          id,
          ...value,
        })),
        blender: {
          name: "Blender Headless",
          mode: "codespaces",
          license: "Blender is free and open source",
          control:
            "Vercel MCP -> free GitHub Codespaces -> Blender -> free Cloudflare Quick Tunnel",
        },
        note: "No paid GPU cloud or paid overage is included.",
      }),
  );

  server.registerTool(
    "get_web_engine_url",
    {
      title: "Get Web Engine URL",
      description:
        "Return the official browser editor URL for one free web engine.",
      inputSchema: z.object({
        engine: z.enum(["godot", "gdevelop", "construct"]),
      }),
    },
    async ({ engine }) => textResult({ id: engine, ...engines[engine] }),
  );

  server.registerTool(
    "free_stack_manifest",
    {
      title: "Free Stack Manifest",
      description:
        "Return the verified free/no-PC stack and its hard cost boundaries.",
    },
    async () =>
      textResult({
        policy: "free-only-no-pc",
        control: "Composio / Custom MCP",
        mcpHosting: "Vercel Hobby",
        cloudDev: "GitHub Codespaces free quota",
        blender: {
          engine: "Blender Headless",
          runtime: "GitHub Codespaces CPU runtime",
          bridge: "Cloudflare Quick Tunnel",
          transport:
            "Vercel Streamable HTTP MCP -> Cloudflare HTTP -> Blender bridge",
        },
        browserEngines: Object.keys(engines),
        desktopGpuEngines: [],
        spendingPolicy:
          "Do not rely on paid overage or paid GPU cloud.",
        tunnelPolicy:
          "Cloudflare Quick Tunnel is free and requires no account; it is temporary and intended for development/testing.",
      }),
  );

  server.registerTool(
    "codespaces_bootstrap",
    {
      title: "Codespaces Bootstrap",
      description:
        "Return the exact free Codespaces bootstrap flow for headless Blender.",
    },
    async () =>
      textResult({
        repository:
          "https://github.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP",
        freeRuntime: "GitHub Codespaces",
        install:
          "bash .devcontainer/install-blender.sh && bash .devcontainer/install-cloudflared.sh",
        start: "bash .devcontainer/start-blender.sh",
        health: "curl http://127.0.0.1:9765/health",
        publicUrlSource:
          "runtime/blender-bridge.json (published by the Codespace runtime)",
      }),
  );

  server.registerTool(
    "desktop_engine_status",
    {
      title: "Desktop Engine Status",
      description:
        "Explain why Unity and Unreal are not provisioned as verified free cloud runtimes.",
      inputSchema: z.object({
        engine: z.enum(["unity", "unreal"]),
      }),
    },
    async ({ engine }) =>
      textResult({
        engine,
        status: "not_provisioned",
        reason:
          "No verified free GPU-backed cloud editor runtime is included.",
        alternative:
          "Use Blender Headless in GitHub Codespaces or the browser-native engines.",
      }),
  );

  server.registerTool(
    "blender_status",
    {
      title: "Blender Status",
      description:
        "Check whether the free headless Blender bridge is reachable.",
    },
    async () =>
      textResult({
        bridge: await callBlender("/health"),
        configSource:
          process.env.BLENDER_BRIDGE_CONFIG_URL ||
          DEFAULT_BRIDGE_CONFIG_URL,
      }),
  );

  server.registerTool(
    "blender_new_scene",
    {
      title: "Blender New Scene",
      description: "Clear the Blender scene.",
    },
    async () => textResult(await callBlender("/scene/new", {})),
  );

  server.registerTool(
    "blender_create_basic_scene",
    {
      title: "Blender Create Basic Scene",
      description:
        "Create an editable 3D game-style test scene with ground, player, obstacle, pickup, camera, and light.",
    },
    async () => textResult(await callBlender("/scene/basic", {})),
  );

  server.registerTool(
    "blender_list_objects",
    {
      title: "Blender List Objects",
      description: "List objects currently in the Blender scene.",
    },
    async () => textResult(await callBlender("/scene/objects")),
  );

  server.registerTool(
    "blender_add_primitive",
    {
      title: "Blender Add Primitive",
      description:
        "Add a mesh primitive with transform and RGB/RGBA material color.",
      inputSchema: z.object({
        primitive: z.enum([
          "cube",
          "sphere",
          "cylinder",
          "cone",
          "torus",
          "plane",
        ]),
        name: z.string().optional(),
        location: z
          .tuple([z.number(), z.number(), z.number()])
          .optional(),
        rotation: z
          .tuple([z.number(), z.number(), z.number()])
          .optional(),
        scale: z.tuple([z.number(), z.number(), z.number()]).optional(),
        color: z
          .union([
            z.tuple([z.number(), z.number(), z.number()]),
            z.tuple([z.number(), z.number(), z.number(), z.number()]),
          ])
          .optional(),
      }),
    },
    async (input) => textResult(await callBlender("/object/add", input)),
  );

  server.registerTool(
    "blender_transform_object",
    {
      title: "Blender Transform Object",
      description: "Move, rotate, or scale an existing Blender object.",
      inputSchema: z.object({
        name: z.string(),
        location: z
          .tuple([z.number(), z.number(), z.number()])
          .optional(),
        rotation: z
          .tuple([z.number(), z.number(), z.number()])
          .optional(),
        scale: z.tuple([z.number(), z.number(), z.number()]).optional(),
      }),
    },
    async (input) =>
      textResult(await callBlender("/object/transform", input)),
  );

  server.registerTool(
    "blender_delete_object",
    {
      title: "Blender Delete Object",
      description: "Delete an existing Blender object by name.",
      inputSchema: z.object({ name: z.string() }),
    },
    async (input) => textResult(await callBlender("/object/delete", input)),
  );

  server.registerTool(
    "blender_save_blend",
    {
      title: "Blender Save Blend",
      description:
        "Save the current Blender scene into the Codespace output directory.",
      inputSchema: z.object({ filename: z.string().optional() }),
    },
    async (input) => textResult(await callBlender("/scene/save", input)),
  );

  server.registerTool(
    "blender_render",
    {
      title: "Blender Render",
      description:
        "Render the current Blender scene to a PNG using Blender Eevee.",
      inputSchema: z.object({
        filename: z.string().optional(),
        width: z.number().int().min(320).max(1280).optional(),
        height: z.number().int().min(180).max(720).optional(),
      }),
    },
    async (input) => {
      const result = await callBlender("/scene/render", input);
      return textResult({
        ...result,
        artifactUrl: await artifactUrlFor(result.filename),
      });
    },
  );

  server.registerTool(
    "blender_export_glb",
    {
      title: "Blender Export GLB",
      description: "Export the current Blender scene as a GLB artifact.",
      inputSchema: z.object({ filename: z.string().optional() }),
    },
    async (input) => {
      const result = await callBlender("/scene/export-glb", input);
      return textResult({
        ...result,
        artifactUrl: await artifactUrlFor(result.filename),
      });
    },
  );
});

export { handler as GET, handler as POST };
