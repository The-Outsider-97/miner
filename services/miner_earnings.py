"""Authoritative Miner earnings state.

Current Bittensor Dynamic TAO miner rewards are subnet-alpha emissions. Miner/Harnyx does not currently expose an authoritative cumulative
SN67 TAO-earned ledger, so this service intentionally refuses to reinterpret wallet balance, stake, current emission, or alpha value
as cumulative TAO earnings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..utils.config_loader import get_config_section


def get_miner_earnings_state() -> dict[str, Any]:
    project = get_config_section("project")
    netuid = int(project.get("netuid", 67))

    return {
        "status": "unavailable",
        "netuid": netuid,
        "earned_tao": None,
        "source": "bittensor",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "message": (
            "Cumulative SN67 TAO earnings cannot currently be determined authoritatively. Bittensor Dynamic TAO miner rewards are subnet-alpha emissions;"
            "wallet balance, stake, current emission, and current alpha value are not equivalent to cumulative TAO earned."
        ),
    }