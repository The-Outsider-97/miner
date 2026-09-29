"""Miner-owned path, external-repository and subprocess helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .miner_errors import BenchmarkExecutionError, ExternalDependencyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_ROOT = PROJECT_ROOT / "external"


def require_external_repository(name: str, sentinel: str) -> Path:
    root = (EXTERNAL_ROOT / name).resolve()
    expected = root / sentinel
    if not expected.is_file():
        raise ExternalDependencyError(
            f"external/{name} is not initialized at the expected revision; run git submodule update --init --recursive",
            context={"repository": name, "expected_file": str(expected)},
        )
    return root


def prepend_import_path(path: Path) -> None:
    value = str(path.resolve())
    if value not in sys.path:
        sys.path.insert(0, value)


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise ExternalDependencyError(
            "unable to resolve git revision",
            context={"path": str(path), "stderr": completed.stderr.strip()[-500:]},
        )
    return completed.stdout.strip()


def run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float | None = None,
    env_overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(dict(env_overrides or {}))
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise BenchmarkExecutionError(
            f"required executable was not found: {command[0]}",
            context={"cwd": str(cwd)},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BenchmarkExecutionError(
            "external command exceeded its allowed execution time",
            context={"cwd": str(cwd), "timeout_seconds": timeout},
        ) from exc
    if completed.returncode != 0:
        raise BenchmarkExecutionError(
            "external command failed",
            context={
                "cwd": str(cwd),
                "returncode": completed.returncode,
                "command": list(command),
                "stderr_tail": completed.stderr.strip()[-2000:],
            },
        )
    return completed
