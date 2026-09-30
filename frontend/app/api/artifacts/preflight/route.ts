import { NextResponse } from "next/server";

import { runMinerJson } from "../../../../lib/server/minerPython";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SHA256 = /^[0-9a-f]{64}$/i;

export async function POST(request: Request) {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error: "Malformed JSON request.",
      },
      { status: 400 },
    );
  }

  if (
    typeof body !== "object" ||
    body === null ||
    !("artifact_sha256" in body) ||
    typeof body.artifact_sha256 !== "string" ||
    !SHA256.test(body.artifact_sha256)
  ) {
    return NextResponse.json(
      {
        ok: false,
        error: "Invalid artifact SHA-256.",
      },
      { status: 400 },
    );
  }

  try {
    const result = await runMinerJson<{
      ok: boolean;
      http_status?: number;
      error?: string;
      preflight?: unknown;
    }>(
      "miner.submission_api",
      ["preflight"],
      {
        stdin: JSON.stringify({
          artifact_sha256:
            body.artifact_sha256.toLowerCase(),
        }),
        timeoutMs: 150_000,
      },
    );

    return NextResponse.json(result, {
      status:
        result.ok
          ? 200
          : result.http_status ?? 400,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Artifact preflight is unavailable.",
      },
      { status: 503 },
    );
  }
}