import {
  Client,
  StreamableHTTPClientTransport,
  fromJsonSchema,
} from "@modelcontextprotocol/sdk/client";
import type { McpServer } from "@modelcontextprotocol/sdk/server";

export type RemoteMcpProvider = {
  id: string;
  name: string;
  description?: string;
  url?: string;
  urlEnv?: string;
  urlEnvFallback?: string;
  urlSuffix?: string;
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

const DEFAULT_REGISTRY_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/free-mcp-providers.json";

const DEFAULT_CAPABILITY_MATRIX_URL =
  "https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/free-game-capability-matrix.json";

const registryCache: { expiresAt: number; registry: Registry } | null = null;
const capabilityCache: { expiresAt: number; matrix: CapabilityMatrix } | null = null;

let cachedRegistry: { expiresAt: number; registry: Registry } | null = null;
let cachedCapabilities: { expiresAt: number; matrix: CapabilityMatrix } | null =
  null;

const remoteCache = new Map<
  string,
  { expiresAt: number; entry?: ConnectedProvider; error?: string }
>();

const DISCOVERY_TTL_MS = 15_000;
const METADATA_TTL_MS = 60_000;
const CONNECT_TIMEOUT_MS = 20_000;

function now() {
  return Date.now();
}

function registryUrl() {
  return (
    process.env.HYOUKA_MCP_REGISTRY_URL?.trim() ||
    DEFAULT_REGISTRY_URL
  );
}

function capabilityMatrixUrl() {
  return (
    process.env.HYOUKA_CAPABILITY_MATRIX_URL?.trim() ||
    DEFAULT_CAPABILITY_MATRIX_URL
  );
}

async function loadRegistry(): Promise<Registry> {
  const t = now();
  if (cachedRegistry && cachedRegistry.expiresAt > t) {
    return cachedRegistry.registry;
  }

  const response = await fetch(registryUrl() + "?t=" + t, {
    cache: "no-store",
    headers: {
      "cache-control": "no-cache",
      pragma: "no-cache",
    },
  });

  if (!response.ok) {
    throw new Error("Remote MCP registry fetch failed: HTTP " + response.status);
  }

  const value = (await response.json()) as Partial<Registry>;
  const registry: Registry =
    typeof value.version === "string" && Array.isArray(value.providers)
      ? value as Registry
      : { version: "invalid", providers: [] };

  cachedRegistry = { expiresAt: t + METADATA_TTL_MS, registry };
  return registry;
}

async function loadCapabilityMatrix(): Promise<CapabilityMatrix> {
  const t = now();
  if (cachedCapabilities && cachedCapabilities.expiresAt > t) {
    return cachedCapabilities.matrix;
  }

  const response = await fetch(capabilityMatrixUrl() + "?t=" + t, {
    cache: "no-store",
    headers: {
      "cache-control": "no-cache",
      pragma: "no-cache",
    },
  });

  if (!response.ok) {
    throw new Error(
      "Capability matrix fetch failed: HTTP " + response.status,
    );
  }

  const value = (await response.json()) as Partial<CapabilityMatrix>;
  const matrix: CapabilityMatrix =
    typeof value.version === "string" &&
    typeof value.goal === "string" &&
    Array.isArray(value.domains)
      ? value as CapabilityMatrix
      : { version: "invalid", goal: "unknown", domains: [] };

  cachedCapabilities = {
    expiresAt: t + METADATA_TTL_MS,
    matrix,
  };
  return matrix;
}

function resolveUrl(provider: RemoteMcpProvider): string | null {
  const envKeys = [provider.urlEnv, provider.urlEnvFallback].filter(
    (key): key is string => typeof key === "string" && key.length > 0,
  );

  let raw: string | null = null;
  for (const key of envKeys) {
    const value = process.env[key]?.trim();
    if (value) {
      raw = value;
      break;
    }
  }

  if (!raw) {
    raw = provider.url?.trim() || null;
  }

  if (!raw) return null;

  const normalized = raw.replace(/\/$/, "");
  if (!provider.urlSuffix) return normalized;

  const suffix = provider.urlSuffix.startsWith("/")
    ? provider.urlSuffix
    : "/" + provider.urlSuffix;

  if (normalized.endsWith(suffix)) return normalized;
  return normalized + suffix;
}

function bearerToken(provider: RemoteMcpProvider): string | undefined {
  if (!provider.tokenEnv) return undefined;
  return process.env[provider.tokenEnv]?.trim() || undefined;
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
    version: "1.3.0",
  });

  await Promise.race([
    client.connect(transport),
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error("provider connect timeout")),
        CONNECT_TIMEOUT_MS,
      ),
    ),
  ]);

  const listed = await Promise.race([
    client.listTools(),
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error("tools/list timeout")),
        CONNECT_TIMEOUT_MS,
      ),
    ),
  ]);

  return {
    provider,
    client,
    tools: (listed.tools ?? []).map((tool) => ({
      name: String(tool.name),
      description:
        typeof tool.description === "string" ? tool.description : undefined,
      inputSchema:
        tool.inputSchema &&
        typeof tool.inputSchema === "object" &&
        !Array.isArray(tool.inputSchema)
          ? (tool.inputSchema as Record<string, unknown>)
          : { type: "object", properties: {} },
    })),
  };
}

async function getConnectedProviders(): Promise<ConnectedProvider[]> {
  const registry = await loadRegistry();

  const candidates = registry.providers
    .filter((provider) => provider.enabled !== false)
    .map((provider) => ({
      provider,
      url: resolveUrl(provider),
    }))
    .filter(
      (item): item is { provider: RemoteMcpProvider; url: string } =>
        Boolean(item.url),
    );

  const t = now();
  const results = await Promise.all(
    candidates.map(async ({ provider, url }) => {
      const cached = remoteCache.get(provider.id);
      if (cached && cached.expiresAt > t) {
        return cached.entry;
      }

      try {
        const entry = await connectProvider(provider, url);
        remoteCache.set(provider.id, {
          expiresAt: now() + DISCOVERY_TTL_MS,
          entry,
        });
        return entry;
      } catch (error) {
        remoteCache.set(provider.id, {
          expiresAt: now() + DISCOVERY_TTL_MS,
          error: String(error),
        });
        return undefined;
      }
    }),
  );

  return results.filter(
    (entry): entry is ConnectedProvider => Boolean(entry),
  );
}

export function refreshRemoteMcpCaches() {
  cachedRegistry = null;
  cachedCapabilities = null;
  remoteCache.clear();
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

export async function remoteMcpToolInventory() {
  const entries = await getConnectedProviders();
  return {
    providers: entries.map((entry) => ({
      id: entry.provider.id,
      name: entry.provider.name,
      source: entry.provider.source ?? null,
      toolCount: entry.tools.length,
      tools: entry.tools.map((tool) => ({
        name: tool.name,
        description: tool.description ?? null,
      })),
    })),
    totalToolCount: entries.reduce(
      (sum, entry) => sum + entry.tools.length,
      0,
    ),
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
    name =
      (normalized || "mcp_remote_tool").slice(0, 128 - tail.length) + tail;
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
          tool.description ??
          "Dynamically discovered tool from remote MCP provider " +
            tool.provider.id +
            ".",
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

export async function remoteMcpStatus() {
  try {
    await getConnectedProviders();
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
        toolCount: cached?.entry?.tools.length ?? 0,
        toolNames: cached?.entry?.tools.map((tool) => tool.name) ?? [],
        error: cached?.error ?? null,
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

    const connectedToolCount = remote.providers.reduce(
      (sum, provider) => sum + provider.toolCount,
      0,
    );

    return {
      matrixVersion: matrix.version,
      goal: matrix.goal,
      domains: matrix.domains,
      remoteProviders: remote.providers,
      connectedToolCount,
      dynamicDiscovery: {
        registry: true,
        providers: remote.providers.length,
        toolsListDiscovery: true,
        providerLimit: "uncapped-by-gateway",
      },
    };
  } catch (error) {
    return {
      matrixVersion: "unknown",
      goal: "unknown",
      domains: [],
      remoteProviders: [],
      connectedToolCount: 0,
      dynamicDiscovery: {
        registry: false,
        providers: 0,
        toolsListDiscovery: false,
        providerLimit: "uncapped-by-gateway",
      },
      error: String(error),
    };
  }
}
