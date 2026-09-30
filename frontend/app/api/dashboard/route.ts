import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SLAI_ROOT = path.resolve(process.cwd(), "..", "..");
const MINER_ROOT = path.join(SLAI_ROOT, "miner");

const DASHBOARD_API = path.join(MINER_ROOT, "dashboard_api.py");
const SLAI_MINER = path.join(SLAI_ROOT, "slai_miner.py");

function getPythonExecutable(): string {
  if (process.env.MINER_PYTHON) {
    return process.env.MINER_PYTHON;
  }

  const candidates =
    process.platform === "win32"
      ? [
          path.join(SLAI_ROOT, "venv", "Scripts", "python.exe"),
          path.join(SLAI_ROOT, ".venv", "Scripts", "python.exe"),
        ]
      : [
          path.join(SLAI_ROOT, "venv", "bin", "python"),
          path.join(SLAI_ROOT, ".venv", "bin", "python"),
        ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return process.platform === "win32" ? "python.exe" : "python3";
}

function runDashboardApi(): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(DASHBOARD_API)) {
      reject(
        new Error(
          `dashboard_api.py was not found at ${DASHBOARD_API}`
        )
      );
      return;
    }

    const python = getPythonExecutable();

    const child = spawn(
      python,
      [DASHBOARD_API],
      {
        cwd: MINER_ROOT,
        env: {
          ...process.env,
          SLAI_ROOT,
          SLAI_MINER_PATH: SLAI_MINER,
          PYTHONUNBUFFERED: "1",
        },
        windowsHide: true,
      }
    );

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    child.on("error", (error) => {
      reject(error);
    });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            stderr.trim() ||
              `dashboard_api.py exited with code ${code}`
          )
        );
        return;
      }

      resolve(stdout.trim());
    });
  });
}

export async function GET() {
  try {
    const output = await runDashboardApi();

    if (!output) {
      return NextResponse.json(
        {
          error: "dashboard_api.py returned no data",
        },
        {
          status: 503,
          headers: {
            "Cache-Control": "no-store",
          },
        }
      );
    }

    const data = JSON.parse(output);

    return NextResponse.json(data, {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : String(error);

    console.error("Dashboard API failed:", message);

    return NextResponse.json(
      {
        error: message,
      },
      {
        status: 503,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }
}
