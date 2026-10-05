from __future__ import annotations

from types import SimpleNamespace

from miner.services import bittensor_state


def _completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_unregistered_hotkey_is_explicit(monkeypatch) -> None:
    outputs = iter(
        [
            _completed("null"),
            _completed('"τ0.015"'),
            _completed('{"block": 1000, "num_uids": 256, "max_uids": 256, "immunity_period": 14400}'),
        ]
    )
    monkeypatch.setattr(bittensor_state.subprocess, "run", lambda *a, **k: next(outputs))

    snapshot = bittensor_state.build_bittensor_snapshot(
        netuid=67,
        wallet_name="slai",
        hotkey_name="sn67",
    )

    assert snapshot["status"] == "not_registered"
    assert snapshot["registered"]["value"] is False
    assert snapshot["uid"]["value"] is None
    assert snapshot["subnet_full"]["value"] is True
    assert snapshot["registration_burn"]["value"] == "τ0.015"


def test_registered_hotkey_calculates_immunity(monkeypatch) -> None:
    metagraph = {
        "block": 12000,
        "num_uids": 2,
        "max_uids": 256,
        "immunity_period": 14400,
        "block_at_registration": [100, 10000],
        "emission": [0, 7],
        "incentives": [0, 3],
        "consensus": [0, 2],
        "active": [False, True],
        "last_update": [0, 11900],
    }
    import json

    outputs = iter([_completed("1"), _completed('"τ0.02"'), _completed(json.dumps(metagraph))])
    monkeypatch.setattr(bittensor_state.subprocess, "run", lambda *a, **k: next(outputs))

    snapshot = bittensor_state.build_bittensor_snapshot(
        netuid=67,
        wallet_name="slai",
        hotkey_name="sn67",
    )

    assert snapshot["status"] == "registered"
    assert snapshot["uid"]["value"] == 1
    assert snapshot["registration_block"]["value"] == 10000
    assert snapshot["immunity_blocks_remaining"]["value"] == 12400
    assert snapshot["emission"]["value"] == 7
    assert snapshot["active"]["value"] is True


def test_missing_btcli_degrades_without_fabricating_state(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(bittensor_state.subprocess, "run", missing)
    snapshot = bittensor_state.build_bittensor_snapshot(
        netuid=67,
        wallet_name="slai",
        hotkey_name="sn67",
    )
    assert snapshot["status"] == "api_unavailable"
    assert snapshot["registered"]["value"] is None
    assert snapshot["registered"]["freshness"] == "unavailable"
