import { NextResponse } from "next/server";

import { runMinerJson } from "../../../lib/server/minerPython";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type DashboardResponse = {
  schema?: unknown;
};

type MiningResponse = {
  status?: unknown;
  active?: unknown;
};

const unknownMiningState = {
  status: "unknown",
  active: false,
  batch_id: null,
  batch_status: null,
  artifact_id: null,
  source: "harnyx_public_monitoring",
  checked_at: null,
} as const;

export async function GET() {
  try {
    const [data, mining] = await Promise.all([
      runMinerJson<DashboardResponse>(
        "miner.dashboard_api",
        ["--json"],
      ),
      runMinerJson<MiningResponse>(
        "miner.mining_status_api",
        ["--json"],
      ).catch(() => unknownMiningState),
    ]);

    if (data.schema !== "slai-miner-dashboard-v1") {
      throw new Error(
        "Unsupported Miner dashboard schema.",
      );
    }

    const safeMining =
      mining.active === true &&
      mining.status === "mining"
        ? mining
        : {
            ...mining,
            active: false,
          };

    return NextResponse.json(
      {
        ...data,
        mining: safeMining,
      },
      {
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  } catch {
    return NextResponse.json(
      {
        error:
          "Miner dashboard backend is unavailable.",
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
