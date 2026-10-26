import { NextResponse } from "next/server";

import { runMinerJson } from "../../../lib/server/minerPython";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const result = await runMinerJson<{
      ok: boolean;
      artifacts?: unknown[];
      error?: string;
    }>(
      "miner.submission_api",
      ["list"],
    );

    return NextResponse.json(result, {
      status: result.ok ? 200 : 503,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Artifact discovery is unavailable.",
      },
      {
        status: 503,
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  }
}