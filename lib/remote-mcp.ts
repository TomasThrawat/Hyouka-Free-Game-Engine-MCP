import { Client, StreamableHTTPClientTransport, fromJsonSchema } from "@modelcontextprotocol/client";

export type RemoteMcpProvider = {
  id: string;
  name: string;
  description?: string;
  url?: string;
  urlEnv?: string;
  tokenEnv?: string;
  enabled?: boolean;
  source?: string;
  license?: string;
  capabilities?: string[];
};

type RemoteEntry = {
  provider: RemoteMcpProvider;
  client: Client;
  tools: Array<{
    name: string;
    description?: string;
    inputSchema?: Record<string, unknown>;
  }>;
};

type Registry = {
  version: string;
  providers: RemoteMcpProvider[];
};

const REGISTRY_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/free-mcp-providers.json";

let registryCache: { expiresAt: number; registry: Registry } | null = null;
const remoteCache = new Map<
  string,
  { expiresAt: number; entry?: RemoteEntry; error?: string }
>();

async function loadRegistry(): Promise<Registry> {
  const now = Date.now();
  if (registryCache && registryCache.expiresAt > now) {
    return registryCache.registry;
  }

  const response = await fetch(REGISTRY_URL + "?t=" + now, {
    cache: "no-store",
    headers: { "cache-control": "no-cache", pragma: "no-cache" },
  });

  if (!response.ok) {
    throw new Error("Remote MCP registry fetch failed: HTTP " + response.status);
  }

  const value = (await response.json()) as Registry;
  const registry =
    value &&
    typeof value.version === "string" &&
    Array.isArray(value.providers)
      ? value
      : { version: "invalid", providers: [] };

  registryCache = { expiresAt: now + 60_000, registry };
  return registry;
}

function resolveUrl(provider: RemoteMcpProvider): string | null {
  if (provider.urlEnv) {
    const value = process.env[provider.urlEnv]?.trim();
    if (value) {
      return value.replace(/\/$/, "");
    }
  }

  return provider.url?.trim().replace(/\/$/, "") || null;
}

function bearerToken(provider: RemoteMcpProvider): string | undefined {
  if (!provider.tokenEnv) return undefined;
  const value = process.env[provider.tokenEnv]?.trim();
  return value || undefined;
}

async function connectProvider(
  provider: RemoteMcpProvider,
  url: string,
): Promise<RemoteEntry> {
  const token = bearerToken(provider);
  const transport = new StreamableHTTPClientTransport(new URL(url), {
    requestInit: token
      ? {
          headers: {
            authorization: "Bearer " + token,
          },
        }
      : undefined,
  });

  const client = new Client({
    name: "hyouka-free-game-engine-mcp",
    version: "1.1.0",
  });

  await client.connect(transport);

  const listed = await client.listTools();
  return {
    provider,
    client,
    tools: (listed.tools ?? []).map((tool) => ({
      name: String(tool.name),
      description:
        typeof tool.description === "string"
          ? tool.description
          : undefined,
      inputSchema:
        tool.inputSchema && typeof tool.inputSchema === "object"
          ? (tool.inputSchema as Record<string, unknown>)
          : { type: "object", properties: {} },
    })),
  };
}

function uniqueName(base: string, used: Set<string>): string {
  const normalized = ("mcp_" + base.replace(/[^A-Za-z0-9_.-]/g, "_")).slice(
    0,
    120,
  );
  let name = normalized || "mcp_remote_tool";
  let suffix = 2;

  while (used.has(name)) {
    const tail = "_" + suffix++;
    name = (normalized || "mcp_remote_tool").slice(
      0,
      128 - tail.length,
    ) + tail;
  }

  used.add(name);
  return name;
}

export async function remoteMcpStatus() {
  try {
    const registry = await loadRegistry();
    const providers = registry.providers.map((provider) => {
      const url = resolveUrl(provider);
      const cached = remoteCache.get(provider.id);
      return {
        id: provider.id,
        name: provider.name,
        enabled: provider.enabled !== false,
        configured: Boolean(url),
        url: url ? new URL(url).origin + new URL(url).pathname : null,
        source: provider.source ?? null,
        license: provider.license ?? null,
        capabilities: provider.capabilities ?? [],
        connected: Boolean(cached?.entry),
        error: cached?.error ?? null,
        toolCount: cached?.entry?.tools.length ?? 0,
      };
    });

    return { version: registry.version, providers };
  } catch (error) {
    return {
      version: "unknown",
      providers: [],
      error: String(error),
    };
  }
}

export async function registerRemoteMcpProviders(
  server: {
    registerTool: (
      name: string,
      config: {
        title?: string;
        description?: string;
        inputSchema?: unknown;
      },
      handler: (args: Record<string, unknown>) => Promise<unknown>,
    ) => void;
  },
  used: Set<string>,
) {
  let registry: Registry;
  try {
    registry = await loadRegistry();
  } catch {
    return;
  }

  const enabled = registry.providers
    .filter((provider) => provider.enabled !== false)
    .map((provider) => ({
      provider,
      url: resolveUrl(provider),
    }))
    .filter(
      (item): item is { provider: RemoteMcpProvider; url: string } =>
        Boolean(item.url),
    )
    .slice(0, 8);

  for (const { provider, url } of enabled) {
    const cached = remoteCache.get(provider.id);
    let entry = cached?.expiresAt && cached.expiresAt > Date.now()
      ? cached.entry
      : undefined;

    if (!entry) {
      try {
        entry = await connectProvider(provider, url);
        remoteCache.set(provider.id, {
          expiresAt: Date.now() + 15_000,
          entry,
        });
      } catch (error) {
        remoteCache.set(provider.id, {
          expiresAt: Date.now() + 15_000,
          error: String(error),
        });
        continue;
      }
    }

    for (const tool of entry.tools) {
      const name = uniqueName(provider.id + "__" + tool.name, used);

      server.registerTool(
        name,
        {
          title: provider.name + ": " + tool.name,
          description:
            tool.description ||
            ("Proxy tool from remote MCP provider " + provider.id + "."),
          inputSchema: fromJsonSchema(
            tool.inputSchema ?? { type: "object", properties: {} },
          ),
        },
        async (args) => {
          const result = await entry!.client.callTool({
            name: tool.name,
            arguments: args,
          });
          return result;
        },
      );
    }
  }
}
