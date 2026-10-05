from __future__ import annotations

from miner import mining_status_api


def _obs(value):
    return {
        "value": value,
        "source": "bittensor_chain",
        "observed_at": "2026-10-05T12:00:00+00:00",
        "freshness": "current",
        "error": None,
    }


def test_chain_not_registered_overrides_harnyx_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        mining_status_api,
        "mining_status_snapshot",
        lambda: {
            "status": "unknown",
            "active": False,
            "phase": "unknown",
            "summary": {"title": "STATUS UNKNOWN"},
            "registration": {"status": "unknown"},
            "onchain": {"status": "unavailable"},
            "batch_id": None,
            "artifact_id": None,
        },
    )
    monkeypatch.setattr(
        mining_status_api,
        "get_config_section",
        lambda section: {"netuid": 67}
        if section == "project"
        else {"wallet_name": "slai", "hotkey_name": "sn67", "query_timeout_seconds": 1.0},
    )
    monkeypatch.setattr(
        mining_status_api,
        "build_bittensor_snapshot",
        lambda **kwargs: {
            "status": "not_registered",
            "netuid": 67,
            "registered": _obs(False),
            "uid": _obs(None),
            "emission": _obs(None),
            "incentive": _obs(None),
            "consensus": _obs(None),
            "active": _obs(None),
            "last_update": _obs(None),
            "registration_block": _obs(None),
            "current_block": _obs(9217114),
            "immunity_period": _obs(14400),
            "immunity_blocks_remaining": _obs(None),
            "registration_burn": _obs("τ0.015964708"),
        },
    )

    snapshot = mining_status_api.build_status_snapshot()
    assert snapshot["phase"] == "not_registered"
    assert snapshot["registration"]["status"] == "not_registered"
    assert snapshot["registration"]["uid"] is None
    assert snapshot["summary"]["title"] == "NOT REGISTERED"
    assert snapshot["network"]["current_block"]["value"] == 9217114


def test_chain_unavailable_does_not_destroy_harnyx_state(monkeypatch) -> None:
    base = {
        "status": "inactive",
        "active": False,
        "phase": "submitted",
        "summary": {"title": "SUBMITTED"},
        "registration": {"status": "unknown"},
        "onchain": {"status": "unavailable"},
    }
    monkeypatch.setattr(mining_status_api, "mining_status_snapshot", lambda: dict(base))
    monkeypatch.setattr(
        mining_status_api,
        "get_config_section",
        lambda section: {"netuid": 67}
        if section == "project"
        else {"wallet_name": "slai", "hotkey_name": "sn67"},
    )
    monkeypatch.setattr(
        mining_status_api,
        "build_bittensor_snapshot",
        lambda **kwargs: {
            "status": "api_unavailable",
            "netuid": 67,
            "registered": {
                "value": None,
                "source": "bittensor_chain",
                "observed_at": "2026-10-05T12:00:00+00:00",
                "freshness": "unavailable",
                "error": "btcli_not_found",
            },
        },
    )

    snapshot = mining_status_api.build_status_snapshot()
    assert snapshot["phase"] == "submitted"
    assert snapshot["summary"]["title"] == "SUBMITTED"
    assert snapshot["network"]["status"] == "api_unavailable"
