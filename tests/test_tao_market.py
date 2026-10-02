from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from miner.services import tao_market  # noqa: E402


def test_cryptoapis_parser_reads_rate_and_timestamp() -> None:
    payload = {
        "data": {
            "item": {
                "calculationTimestamp": 1_700_000_000,
                "rate": "123.456",
            }
        }
    }
    rate, timestamp = tao_market._parse_cryptoapis(json.dumps(payload), "USD")
    assert rate == "123.456"
    assert timestamp == 1_700_000_000


def test_freecrypto_parser_accepts_nested_conversion() -> None:
    payload = {"data": {"converted_amount": "42.25"}}
    assert tao_market._parse_freecrypto(json.dumps(payload), "EUR") == "42.25"


def test_coinapi_parser_requires_all_requested_currencies() -> None:
    payload = {
        "rates": [
            {"asset_id_quote": "USD", "rate": 100, "time": "2026-09-30T20:00:00Z"},
            {"asset_id_quote": "EUR", "rate": 90, "time": "2026-09-30T20:00:01Z"},
            {"asset_id_quote": "GBP", "rate": 80, "time": "2026-09-30T20:00:02Z"},
        ]
    }
    prices, updated = tao_market._parse_coinapi(json.dumps(payload), tao_market._SUPPORTED)
    assert prices == {
        "USD": "100",
        "EUR": "90",
        "GBP": "80",
    }
    assert updated == "2026-09-30T20:00:00+00:00"


def test_provider_index_rotates_after_successful_provider() -> None:
    cache = {"provider": "freecryptoapi"}
    assert tao_market._next_provider_index(cache, 3) == 2


def test_persisted_provider_index_takes_priority() -> None:
    cache = {"provider": "cryptoapis", "next_provider_index": 2}
    assert tao_market._next_provider_index(cache, 3) == 2


def test_cache_refresh_window_uses_persisted_due_time() -> None:
    cache = {"fetched_epoch": 1_000, "next_refresh_epoch": 1_240}
    assert tao_market._cache_is_fresh(cache, 1_239, 300) is True
    assert tao_market._cache_is_fresh(cache, 1_240, 300) is False
