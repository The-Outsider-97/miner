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
    bootstrap = f"""
import importlib
import importlib.util
import sys
from pathlib import Path

root = Path({str(ROOT)!r})

spec = importlib.util.spec_from_file_location(
    "miner",
    root / "__init__.py",
    submodule_search_locations=[str(root)],
)

if spec is None or spec.loader is None:
    raise RuntimeError("Unable to bootstrap Miner package")

package = importlib.util.module_from_spec(spec)
sys.modules["miner"] = package
spec.loader.exec_module(package)

importlib.import_module("miner.{module_name}")
"""

    completed = subprocess.run(
        [sys.executable, "-c", bootstrap],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, (
        f"{module_name} import failed\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
