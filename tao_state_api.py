"""Frontend-safe TAO market and Miner earnings snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .services.miner_earnings import get_miner_earnings_state
from .services.tao_market import get_tao_market_state


def build_tao_snapshot() -> dict[str, Any]:
    return {
        "schema": "slai-miner-tao-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": get_tao_market_state(),
        "earnings": get_miner_earnings_state(),
    }


def main() -> int:
    print(
        json.dumps(
            build_tao_snapshot(),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())