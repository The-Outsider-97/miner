"""Read-only Bittensor chain observability for the miner dashboard.

This module never registers, stakes, transfers, or mutates wallet state. It uses
btcli as an external read-only chain client and degrades independently when the
CLI or RPC is unavailable.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils.miner_helpers import PROJECT_ROOT


@dataclass(frozen=True, slots=True)
class ChainObservation:
    value: Any
    source: str
    observed_at: str
    freshness: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_bittensor_snapshot(
    *,
    netuid: int,
    wallet_name: str,
    hotkey_name: str,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).isoformat()
    hotkey_ref = f"{wallet_name}/{hotkey_name}"

    uid_result = _query_json(
        ["btcli", "query", "uid", "--netuid", str(netuid), "--hotkey", hotkey_ref, "--json"],
        timeout_seconds,
    )
    burn_result = _query_json(
        ["btcli", "query", "burn", "--netuid", str(netuid), "--json"],
        timeout_seconds,
    )
    metagraph_result = _query_json(
        ["btcli", "query", "metagraph", "--netuid", str(netuid), "--json"],
        timeout_seconds,
    )

    uid = _normalize_uid(uid_result.value)
    registered = None if uid_result.error else uid is not None

    meta = metagraph_result.value if isinstance(metagraph_result.value, dict) else {}
    current_block = _integer(meta.get("block"))
    num_uids = _integer(meta.get("num_uids"))
    max_uids = _integer(meta.get("max_uids"))
    immunity_period = _integer(meta.get("immunity_period"))

    registration_block = None
    emission = None
    incentive = None
    consensus = None
    active = None
    last_update = None
    if uid is not None:
        registration_block = _indexed(meta.get("block_at_registration"), uid)
        emission = _indexed(meta.get("emission"), uid)
        incentive = _indexed(meta.get("incentives"), uid)
        consensus = _indexed(meta.get("consensus"), uid)
        active = _indexed(meta.get("active"), uid)
        last_update = _indexed(meta.get("last_update"), uid)

    immunity_remaining = None
    if (
        current_block is not None
        and registration_block is not None
        and immunity_period is not None
    ):
        immunity_remaining = max(0, immunity_period - (current_block - registration_block))

    status = "api_unavailable" if uid_result.error else ("registered" if registered else "not_registered")
    return {
        "status": status,
        "netuid": netuid,
        "wallet_name": wallet_name,
        "hotkey_name": hotkey_name,
        "hotkey_ref": hotkey_ref,
        "registered": _observation(registered, observed_at, uid_result.error),
        "uid": _observation(uid, observed_at, uid_result.error),
        "current_block": _observation(current_block, observed_at, metagraph_result.error),
        "registration_block": _observation(registration_block, observed_at, metagraph_result.error),
        "immunity_period": _observation(immunity_period, observed_at, metagraph_result.error),
        "immunity_blocks_remaining": _observation(immunity_remaining, observed_at, metagraph_result.error),
        "num_uids": _observation(num_uids, observed_at, metagraph_result.error),
        "max_uids": _observation(max_uids, observed_at, metagraph_result.error),
        "subnet_full": _observation(
            None if num_uids is None or max_uids is None else num_uids >= max_uids,
            observed_at,
            metagraph_result.error,
        ),
        "emission": _observation(emission, observed_at, metagraph_result.error),
        "incentive": _observation(incentive, observed_at, metagraph_result.error),
        "consensus": _observation(consensus, observed_at, metagraph_result.error),
        "active": _observation(active, observed_at, metagraph_result.error),
        "last_update": _observation(last_update, observed_at, metagraph_result.error),
        "registration_burn": _observation(burn_result.value, observed_at, burn_result.error),
    }


def _observation(value: Any, observed_at: str, error: str | None) -> dict[str, Any]:
    return ChainObservation(
        value=value,
        source="bittensor_chain",
        observed_at=observed_at,
        freshness="unavailable" if error else "current",
        error=error,
    ).to_dict()


@dataclass(frozen=True, slots=True)
class _QueryResult:
    value: Any
    error: str | None = None


def _query_json(command: list[str], timeout_seconds: float) -> _QueryResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return _QueryResult(None, "btcli_not_found")
    except subprocess.TimeoutExpired:
        return _QueryResult(None, "btcli_timeout")
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-300:] or f"exit_{completed.returncode}"
        return _QueryResult(None, detail)

    payload = completed.stdout.strip()
    try:
        return _QueryResult(json.loads(payload))
    except json.JSONDecodeError:
        lowered = payload.lower()
        if lowered in {"none", "null"}:
            return _QueryResult(None)
        return _QueryResult(payload or None)


def _normalize_uid(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        for key in ("uid", "value"):
            if key in value:
                return _normalize_uid(value[key])
    text = str(value).strip().lower()
    if text in {"", "none", "null"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _indexed(value: Any, uid: int) -> Any:
    if isinstance(value, list) and 0 <= uid < len(value):
        return value[uid]
    if isinstance(value, tuple) and 0 <= uid < len(value):
        return value[uid]
    return None
