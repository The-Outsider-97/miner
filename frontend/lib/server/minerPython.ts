import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const DEFAULT_TIMEOUT_MS = 20_000;
const MAX_STDOUT_BYTES = 4 * 1024 * 1024;

export function minerRoot(): string {
  const configured = process.env.MINER_ROOT?.trim();

  if (configured) {
    return path.resolve(configured);
  }

  return path.resolve(process.cwd(), "..");
}

export function slaiRoot(): string {
  return path.dirname(minerRoot());
}

function pythonExecutable(): string {
  const configured = process.env.MINER_PYTHON?.trim();

  if (configured) {
    return configured;
  }

  const root = slaiRoot();
  const miner = minerRoot();

  const candidates =
    process.platform === "win32"
      ? [
          path.join(root, "venv", "Scripts", "python.exe"),
          path.join(root, ".venv", "Scripts", "python.exe"),
          path.join(miner, ".venv", "Scripts", "python.exe"),
        ]
      : [
          path.join(root, "venv", "bin", "python"),
          path.join(root, ".venv", "bin", "python"),
          path.join(miner, ".venv", "bin", "python"),
        ];

  const available = candidates.find((candidate) =>
    fs.existsSync(candidate),
  );

  if (available) {
    return available;
  }

  return process.platform === "win32"
    ? "python.exe"
    : "python3";
}

type RunOptions = {
  stdin?: string;
  timeoutMs?: number;
};

export async function runMinerJson<T>(
  moduleName: string,
  args: readonly string[] = [],
  options: RunOptions = {},
): Promise<T> {
  const executable = pythonExecutable();
  const cwd = slaiRoot();
  const timeoutMs =
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return await new Promise<T>((resolve, reject) => {
    const child = spawn(
      executable,
      ["-m", moduleName, ...args],
      {
        cwd,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
        },
        shell: false,
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );

    let stdout = "";
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

      finish(() =>
        reject(
          new Error("Miner backend request timed out."),
        ),
      );
    }, timeoutMs);

    child.stdout.setEncoding("utf8");

    child.stdout.on("data", (chunk: string) => {
      stdoutBytes += Buffer.byteLength(
        chunk,
        "utf8",
      );

      if (stdoutBytes > MAX_STDOUT_BYTES) {
        child.kill();

        finish(() =>
          reject(
            new Error(
              "Miner backend response exceeded the safety limit.",
            ),
          ),
        );

        return;
      }

      stdout += chunk;
    });

    child.on("error", () => {
      finish(() =>
        reject(
          new Error(
            "Miner backend process could not be started.",
          ),
        ),
      );
    });

    child.on("close", (code) => {
      finish(() => {
        if (code !== 0) {
          reject(
            new Error(
              "Miner backend process failed.",
            ),
          );

          return;
        }

        try {
          resolve(
            JSON.parse(stdout) as T,
          );
        } catch {
          reject(
            new Error(
              "Miner backend returned invalid JSON.",
            ),
          );
        }
      });
    });

    if (options.stdin !== undefined) {
      child.stdin.write(options.stdin);
    }

    child.stdin.end();
  });
}