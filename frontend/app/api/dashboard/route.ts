import { spawn } from "node:child_process";
import path from "node:path";

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DASHBOARD_SCHEMA = "slai-miner-dashboard-v1";
const MAX_STDOUT_BYTES = 4 * 1024 * 1024;
const PROCESS_TIMEOUT_MS = 12_000;

function repositoryRoot(): string {
  const configured = process.env.MINER_ROOT?.trim();
  return configured ? path.resolve(configured) : path.resolve(process.cwd(), "..");
}

function pythonCommand(repoRoot: string): { executable: string; prefix: string[] } {
  const configured = process.env.MINER_PYTHON?.trim();
  if (configured) return { executable: configured, prefix: [] };
  return {
    executable: "uv",
    prefix: ["run", "--project", repoRoot, "--no-sync", "python"],
  };
}

function parseDashboardSnapshot(stdout: string): unknown {
  const value: unknown = JSON.parse(stdout);
  if (
    typeof value !== "object" ||
    value === null ||
    !("schema" in value) ||
    value.schema !== DASHBOARD_SCHEMA
  ) {
    throw new Error("Miner dashboard backend returned an unsupported schema.");
  }
  return value;
}

async function readDashboardSnapshot(): Promise<unknown> {
  const repoRoot = repositoryRoot();
  const scriptPath = path.join(repoRoot, "dashboard_api.py");
  const { executable, prefix } = pythonCommand(repoRoot);

  return await new Promise((resolve, reject) => {
    const child = spawn(executable, [...prefix, scriptPath, "--json"], {
      cwd: repoRoot,
      env: process.env,
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let stdoutBytes = 0;
    let settled = false;

    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      callback();
    };

    const timeout = setTimeout(() => {
      child.kill();
      finish(() => reject(new Error("Miner dashboard backend timed out.")));
    }, PROCESS_TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");

    child.stdout.on("data", (chunk: string) => {
      stdoutBytes += Buffer.byteLength(chunk, "utf8");
      if (stdoutBytes > MAX_STDOUT_BYTES) {
        child.kill();
        finish(() =>
          reject(new Error("Miner dashboard payload exceeded the safety limit.")),
        );
        return;
      }
      stdout += chunk;
    });

    child.stderr.on("data", (chunk: string) => {
      stderr = (stderr + chunk).slice(-4_000);
    });

    child.on("error", (error) => {
      finish(() => reject(error));
    });

    child.on("close", (code) => {
      finish(() => {
        if (code !== 0) {
          reject(
            new Error(
              stderr.trim() ||
                `Miner dashboard backend exited with code ${code ?? "unknown"}.`,
            ),
          );
          return;
        }
        try {
          resolve(parseDashboardSnapshot(stdout));
        } catch (error) {
          reject(
            error instanceof Error
              ? error
              : new Error("Miner dashboard backend returned invalid JSON."),
          );
        }
      });
    });
  });
}

export async function GET() {
  try {
    const snapshot = await readDashboardSnapshot();
    return NextResponse.json(snapshot, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error(
      "Dashboard API failed:",
      error instanceof Error ? error.message : "unknown error",
    );
    return NextResponse.json(
      { error: "Miner dashboard backend is unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
