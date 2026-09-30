import { createDccHttpMcpHandler } from "../../../../lib/dcc-http-mcp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const handlerPromise = createDccHttpMcpHandler("krita");

async function handle(request: Request) {
  const handler = await handlerPromise;
  return handler(request);
}

export const GET = handle;
export const POST = handle;
