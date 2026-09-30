from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MODULES = (
    "benchmark_store",
    "artifact_builder",
    "dashboard_api",
    "slai_miner",
    "adapters.slai",
    "adapters.harnyx",
    "utils.config_loader",
    "utils.miner_errors",
    "utils.miner_helpers",
    "utils.repository_state",
)


@pytest.mark.parametrize("module_name", MODULES)
def test_major_module_imports_independently(module_name: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, (
        f"{module_name} import failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
