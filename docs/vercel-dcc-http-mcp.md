# Blender and Krita HTTP MCP endpoints

The Vercel deployment exposes two MCP-compatible HTTP endpoints:

- Blender: /api/blender/mcp
- Krita: /api/krita/mcp

These routes are serverless HTTP MCP gateways. Vercel does not run the Blender or Krita desktop applications itself. Each route forwards MCP tool discovery and invocation to the configured live DCC provider through lib/dcc-http-mcp.ts.

## Required environment

Set HYOUKA_DCC_HTTP_MCP_TOKEN on Vercel for the gateway bearer token.

The existing provider registry supplies the upstream provider configuration for:

- blender-dcc
- krita

The upstream provider must be reachable over HTTP and configured through the existing provider environment variables/runtime manifest.

## Example

If the Vercel deployment hostname is example.vercel.app:

- https://example.vercel.app/api/blender/mcp
- https://example.vercel.app/api/krita/mcp

Send the bearer token in the Authorization header. The MCP handler supports GET and POST.
