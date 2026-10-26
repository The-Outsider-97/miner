import { NextResponse } from "next/server";
import { evaluateAdminRequest } from "../../../../lib/server/adminGuard";
import { runMinerJson } from "../../../../lib/server/minerPython";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SHA256 = /^[0-9a-f]{64}$/i;

export async function POST(request: Request) {
  // Submission signs an upload with the local hotkey: opt-in, loopback host and
  // same-origin are all required before the request body is even read.
  const env = (
    globalThis as typeof globalThis & {
      process?: { env: Record<string, string | undefined> };
    }
  ).process?.env ?? {};
  const guard = evaluateAdminRequest(request.headers, env, {
    requireOptIn: true,
  });

  if (!guard.allowed) {
    return NextResponse.json(
      {
        ok: false,
        state: "failed",
        error: guard.error,
      },
      {
        status: guard.status,
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  }

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
    !SHA256.test(body.artifact_sha256) ||
    !("confirm" in body) ||
    body.confirm !== true
  ) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Valid artifact SHA-256 and explicit confirmation are required.",
      },
      { status: 400 },
    );
  }

  const allowResubmit =
    "allow_resubmit" in body &&
    body.allow_resubmit === true;

  try {
    const result = await runMinerJson<{
      ok: boolean;
      http_status?: number;
      state?: string;
      error?: string;
      result?: unknown;
    }>(
      "miner.submission_api",
      ["submit"],
      {
        stdin: JSON.stringify({
          artifact_sha256:
            body.artifact_sha256.toLowerCase(),
          confirm: true,
          allow_resubmit: allowResubmit,
        }),
        timeoutMs: 180_000,
      },
    );

    return NextResponse.json(result, {
      status:
        result.ok
          ? 200
          : result.http_status ?? 500,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        state: "failed",
        error: "Artifact submission failed.",
      },
      { status: 503 },
    );
  }
}