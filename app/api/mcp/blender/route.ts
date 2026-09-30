import { createDccHttpMcpHandler } from "../../../../lib/dcc-http-mcp";

export const dynamic = "force-dynamic";

const handlerPromise = createDccHttpMcpHandler("blender-dcc");

async function handle(request: Request) {
  const handler = await handlerPromise;
  return handler(request);
}

export const GET = handle;
export const POST = handle;
export const DELETE = handle;
