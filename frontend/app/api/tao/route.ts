import { NextResponse } from "next/server";

import { runMinerJson } from "../../../lib/server/minerPython";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type TaoResponse = {
  schema?: unknown;
};

export async function GET() {
  try {
    const data = await runMinerJson<TaoResponse>(
      "miner.tao_state_api",
    );

    if (data.schema !== "slai-miner-tao-v1") {
      throw new Error(
        "Unsupported TAO state schema.",
      );
    }

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: "TAO data is unavailable.",
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