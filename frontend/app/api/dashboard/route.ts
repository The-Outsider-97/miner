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
  phase: "unknown",
  summary: {
    title: "STATUS UNKNOWN",
    detail: "Production mining lifecycle data is currently unavailable.",
    next_step: null,
    batch_id: null,
    artifact_id: null,
  },
  registration: {
    status: "unknown",
    netuid: null,
    uid: null,
    hotkey_ss58: null,
    network: null,
    source: "unavailable",
  },
  harnyx_auth: {
    status: "unknown",
    uid: null,
    hotkey_ss58: null,
    message: "Harnyx authentication state is unavailable.",
  },
  providers: {
    status: "unknown",
    required: [],
    configured: [],
    missing: [],
    requirements_complete: false,
  },
  artifact: null,
  scheduler: {
    status: "unknown",
    next_scheduled_batch_at: null,
    cron: null,
    evaluation_timeout_seconds: null,
    validator_health: {
      healthy: null,
      unhealthy: null,
      unknown: null,
    },
  },
  batch: null,
  validator_execution: {
    status: "unknown",
    validator_count: null,
    resolved_count: null,
    total_count: null,
    percent_complete: null,
    started_at: null,
    stage: null,
  },
  evaluation: {
    qualifying_status: "unknown",
    main_status: "unknown",
    main_admitted: null,
    final_status: "unknown",
    qualifying_score: null,
    total_score: null,
    comparison_score: null,
    median_cost_usd: null,
    total_cost_usd: null,
    median_runtime_ms: null,
    novelty_classification: null,
    error_counts: null,
    source: "unavailable",
  },
  allocation: {
    status: "unknown",
    reward_eligible: null,
    weight: null,
    source_batch_id: null,
    source: null,
  },
  onchain: {
    status: "unavailable",
    netuid: null,
    weight_submitted: null,
    incentive: null,
    emission_tao: null,
    rank: null,
    trust: null,
    consensus: null,
    stake: null,
    last_update: null,
    source: "bittensor",
    message: "Bittensor on-chain state is unavailable.",
  },
  errors: ["Miner lifecycle backend is unavailable."],
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
      ).catch((error: unknown) => {
        console.error(
          "[Miner Dashboard] Mining status backend failed:",
          error instanceof Error ? error.message : "Unknown error",
        );

        return unknownMiningState;
      }),
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
