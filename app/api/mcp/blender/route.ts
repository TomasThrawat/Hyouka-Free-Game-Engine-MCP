import { createDccHttpMcpHandler } from "@/lib/dcc-http-mcp";

export const dynamic = "force-dynamic";

const handlerPromise = createDccHttpMcpHandler("blender-dcc");

async function handle(request: Request) {
  const handler = await handlerPromise;
  return handler(request);
}

export { handle as GET, handle as POST, handle as DELETE };
