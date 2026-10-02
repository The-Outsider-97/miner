"""Pytest bootstrap for a checkout-name-independent Miner test environment."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Tests historically use both:
#
#     from utils...
#
# and:
#
#     from miner...
#
# The repository is intentionally not installed as a Python package
# ([tool.uv] package = false), so make both import forms available
# regardless of the checkout directory name.
root_text = str(ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)

if "miner" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "miner",
        ROOT / "__init__.py",
        submodule_search_locations=[root_text],
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to bootstrap Miner package for tests")

    module = importlib.util.module_from_spec(spec)
    sys.modules["miner"] = module
    spec.loader.exec_module(module)
