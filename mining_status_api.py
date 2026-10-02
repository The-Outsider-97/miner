"""Machine-readable frontend bridge for real Harnyx mining state."""

from __future__ import annotations

import argparse
import json

from .services.mining_status import mining_status_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit frontend-safe Miner activity state.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    snapshot = mining_status_snapshot()
    print(
        json.dumps(snapshot, sort_keys=True, default=str)
        if args.json
        else json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
