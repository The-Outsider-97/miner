"""Machine-readable frontend bridge for real Harnyx and Bittensor mining state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support direct invocation from the repository root:
#     uv run python mining_status_api.py --json
#     uv run python -m mining_status_api --json
#
# The repository itself is intentionally not installed as a package. When this
# module is executed directly/top-level, relative imports would otherwise fail.
# Bootstrap the checkout as a package in the same way as slai_miner.py.
if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = package_root.name

from .services.bittensor_state import build_bittensor_snapshot
from .services.mining_status import mining_status_snapshot
from .utils.config_loader import get_config_section


def build_status_snapshot() -> dict:
    """Combine independently failing Harnyx and Bittensor observations."""
    snapshot = mining_status_snapshot()
    project = get_config_section("project")
    bittensor = get_config_section("bittensor")
    chain = build_bittensor_snapshot(
        netuid=int(project.get("netuid", 67)),
        wallet_name=str(bittensor.get("wallet_name") or "slai"),
        hotkey_name=str(bittensor.get("hotkey_name") or "sn67"),
        timeout_seconds=float(bittensor.get("query_timeout_seconds", 12.0)),
    )
    snapshot["network"] = chain

    registered = _value(chain, "registered")
    uid = _value(chain, "uid")
    if chain.get("status") != "api_unavailable":
        snapshot["registration"] = {
            "status": "registered" if registered is True else "not_registered",
            "registered": registered,
            "uid": uid,
            "netuid": chain.get("netuid"),
            "source": "bittensor_chain",
            "checked_at": _observed_at(chain, "registered"),
        }
        snapshot["onchain"] = {
            "status": "emitting"
            if _numeric(_value(chain, "emission")) > 0
            else "registered_no_emission"
            if registered is True
            else "not_registered",
            "netuid": chain.get("netuid"),
            "uid": uid,
            "incentive": _value(chain, "incentive"),
            "emission": _value(chain, "emission"),
            "consensus": _value(chain, "consensus"),
            "active": _value(chain, "active"),
            "last_update": _value(chain, "last_update"),
            "registration_block": _value(chain, "registration_block"),
            "current_block": _value(chain, "current_block"),
            "immunity_period": _value(chain, "immunity_period"),
            "immunity_blocks_remaining": _value(chain, "immunity_blocks_remaining"),
            "registration_burn": _value(chain, "registration_burn"),
            "source": "bittensor_chain",
        }

        if registered is False:
            snapshot["active"] = False
            snapshot["status"] = "inactive"
            snapshot["phase"] = "not_registered"
            snapshot["summary"] = {
                "title": "NOT REGISTERED",
                "detail": "The configured hotkey currently has no SN67 UID on Bittensor.",
                "next_step": "Pass production-readiness checks before considering re-registration.",
                "batch_id": snapshot.get("batch_id"),
                "artifact_id": snapshot.get("artifact_id"),
            }
        elif registered is True and _numeric(_value(chain, "emission")) > 0:
            snapshot["phase"] = "emitting"
            snapshot["summary"] = {
                "title": "EMISSION ACTIVE",
                "detail": "Current Bittensor chain state reports non-zero emission for this UID.",
                "next_step": None,
                "batch_id": snapshot.get("batch_id"),
                "artifact_id": snapshot.get("artifact_id"),
            }

    return snapshot


def _value(chain: dict, key: str):
    observation = chain.get(key)
    return observation.get("value") if isinstance(observation, dict) else None


def _observed_at(chain: dict, key: str):
    observation = chain.get(key)
    return observation.get("observed_at") if isinstance(observation, dict) else None


def _numeric(value) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit frontend-safe Miner activity state.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    snapshot = build_status_snapshot()
    print(
        json.dumps(snapshot, sort_keys=True, default=str)
        if args.json
        else json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
