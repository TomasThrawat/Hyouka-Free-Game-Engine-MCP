import { gameCapabilityAudit } from "../../../lib/remote-mcp";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return Response.json(await gameCapabilityAudit(), {
    headers: {
      "cache-control": "no-store",
    },
  });
}

// Refresh production after DCC credential rotation.
