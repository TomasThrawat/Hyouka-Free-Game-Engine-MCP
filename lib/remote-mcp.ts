import {
  Client,
  StreamableHTTPClientTransport,
  fromJsonSchema,
} from "@modelcontextprotocol/client";
import type { McpServer } from "@modelcontextprotocol/server";

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

export type RemoteMcpTool = {
  provider: RemoteMcpProvider;
  client: Client;
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
};

type Registry = {
  version: string;
  providers: RemoteMcpProvider[];
};

type CapabilityMatrix = {
  version: string;
  goal: string;
  domains: Array<Record<string, unknown>>;
};

type ConnectedProvider = {
  provider: RemoteMcpProvider;
  client: Client;
  tools: Array<{
    name: string;
    description?: string;
    inputSchema: Record<string, unknown>;
  }>;
};

const REGISTRY_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/free-mcp-providers.json";

const CAPABILITY_MATRIX_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/free-game-capability-matrix.json";

let registryCache: { expiresAt: number; registry: Registry } | null = null;
let capabilityCache: {
  expiresAt: number;
  matrix: CapabilityMatrix;
} | null = null;

const remoteCache = new Map<
  string,
  { expiresAt: number; entry?: ConnectedProvider; error?: string }
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

async function loadCapabilityMatrix(): Promise<CapabilityMatrix> {
  const now = Date.now();
  if (capabilityCache && capabilityCache.expiresAt > now) {
    return capabilityCache.matrix;
  }

  const response = await fetch(CAPABILITY_MATRIX_URL + "?t=" + now, {
    cache: "no-store",
    headers: { "cache-control": "no-cache", pragma: "no-cache" },
  });

  if (!response.ok) {
    throw new Error(
      "Capability matrix fetch failed: HTTP " + response.status,
    );
  }

  const value = (await response.json()) as CapabilityMatrix;
  const matrix =
    value &&
    typeof value.version === "string" &&
    typeof value.goal === "string" &&
    Array.isArray(value.domains)
      ? value
      : { version: "invalid", goal: "unknown", domains: [] };

  capabilityCache = { expiresAt: now + 60_000, matrix };
  return matrix;
}

function resolveUrl(provider: RemoteMcpProvider): string | null {
  if (provider.urlEnv) {
    const value = process.env[provider.urlEnv]?.trim();
    if (value) return value.replace(/\/$/, "");
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
): Promise<ConnectedProvider> {
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
    version: "1.2.0",
  });

  await client.connect(transport);
  const listed = await client.listTools();

  return {
    provider,
    client,
    tools: (listed.tools ?? []).map((tool) => ({
      name: String(tool.name),
      description:
        typeof tool.description === "string" ? tool.description : undefined,
      inputSchema:
        tool.inputSchema && typeof tool.inputSchema === "object"
          ? (tool.inputSchema as Record<string, unknown>)
          : { type: "object", properties: {} },
    })),
  };
}

async function getConnectedProviders(): Promise<ConnectedProvider[]> {
  const registry = await loadRegistry();
  const candidates = registry.providers
    .filter((provider) => provider.enabled !== false)
    .map((provider) => ({ provider, url: resolveUrl(provider) }))
    .filter(
      (item): item is { provider: RemoteMcpProvider; url: string } =>
        Boolean(item.url),
    )
    .slice(0, 8);

  const entries: ConnectedProvider[] = [];

  for (const { provider, url } of candidates) {
    const cached = remoteCache.get(provider.id);
    if (cached?.entry && cached.expiresAt > Date.now()) {
      entries.push(cached.entry);
      continue;
    }

    try {
      const entry = await connectProvider(provider, url);
      remoteCache.set(provider.id, {
        expiresAt: Date.now() + 15_000,
        entry,
      });
      entries.push(entry);
    } catch (error) {
      remoteCache.set(provider.id, {
        expiresAt: Date.now() + 15_000,
        error: String(error),
      });
    }
  }

  return entries;
}

export async function discoverRemoteMcpTools(): Promise<RemoteMcpTool[]> {
  const entries = await getConnectedProviders();
  return entries.flatMap((entry) =>
    entry.tools.map((tool) => ({
      provider: entry.provider,
      client: entry.client,
      name: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema,
    })),
  );
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
    name =
      (normalized || "mcp_remote_tool").slice(
        0,
        128 - tail.length,
      ) + tail;
  }

  used.add(name);
  return name;
}

export function registerRemoteMcpTools(
  server: McpServer,
  tools: RemoteMcpTool[],
  used: Set<string>,
) {
  for (const tool of tools) {
    const name = uniqueName(tool.provider.id + "__" + tool.name, used);

    server.registerTool(
      name,
      {
        title: tool.provider.name + ": " + tool.name,
        description:
          tool.description ||
          ("Proxy tool from remote MCP provider " + tool.provider.id + "."),
        inputSchema: fromJsonSchema(tool.inputSchema),
      },
      async (args) =>
        tool.client.callTool({
          name: tool.name,
          arguments: args as Record<string, unknown>,
        }),
    );
  }
}

export async function remoteMcpStatus() {
  try {
    const registry = await loadRegistry();
    const statuses = registry.providers.map((provider) => {
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

    return { version: registry.version, providers: statuses };
  } catch (error) {
    return {
      version: "unknown",
      providers: [],
      error: String(error),
    };
  }
}

export async function gameCapabilityAudit() {
  try {
    const [matrix, remote] = await Promise.all([
      loadCapabilityMatrix(),
      remoteMcpStatus(),
    ]);

    const providerCapabilities = remote.providers.map((provider) => ({
      id: provider.id,
      name: provider.name,
      configured: provider.configured,
      connected: provider.connected,
      toolCount: provider.toolCount,
      capabilities: provider.capabilities,
      error: provider.error,
    }));

    return {
      matrixVersion: matrix.version,
      goal: matrix.goal,
      domains: matrix.domains,
      remoteProviders: providerCapabilities,
      connectedToolCount: providerCapabilities.reduce(
        (sum, provider) => sum + provider.toolCount,
        0,
      ),
    };
  } catch (error) {
    return {
      matrixVersion: "unknown",
      goal: "unknown",
      domains: [],
      remoteProviders: [],
      connectedToolCount: 0,
      error: String(error),
    };
  }
}
