import { createDccHttpMcpHandler } from "../../../../../../lib/dcc-http-mcp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const handler = createDccHttpMcpHandler("blender-dcc");

export const GET = handler;
export const POST = handler;
