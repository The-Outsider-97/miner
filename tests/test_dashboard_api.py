from __future__ import annotations

import json
from pathlib import Path

import miner.dashboard_api as dashboard_api
from miner.benchmark_store import BenchmarkStore
from miner.dashboard_api import _benchmark_snapshot, build_dashboard_snapshot


def _local_eval_report() -> dict:
    return {
        "batch_metadata": {
            "batch": {
                "tasks": [
                    {"task_id": "fast", "query": {"fast": True}},
                    {"task_id": "normal", "query": {"fast": False}},
                ]
            }
        },
        "identifiers": {
            "batch_id": "batch-1",
            "target_artifact_id": "artifact-1",
        },
        "artifacts": {
            "target": {
                "artifact_id": "artifact-1",
                "sha256": "a" * 64,
            }
        },
        "local_result_summary": {
            "head_to_head": {"wins": 1, "losses": 0, "ties": 1},
            "local_champion_selection": {"selected_label": "target"},
            "leaderboard": [],
        },
        "tasks": [
            {
                "task_id": "fast",
                "target": {
                    "score": 0.8,
                    "elapsed_ms": 100.0,
                    "error": None,
                    "cost_and_usage": {
                        "cost_totals": {
                            "total_cost_usd": 0.01,
                            "llm_call_count": 1,
                            "search_tool_call_count": 0,
                            "embedding_call_count": 0,
                        },
                        "token_usage": {"total_tokens": 100},
                        "provider_model_usage": {"chutes": {"model-a": 1}},
                    },
                },
            },
            {
                "task_id": "normal",
                "target": {
                    "score": 0.6,
                    "elapsed_ms": 300.0,
                    "error": None,
                    "cost_and_usage": {
                        "cost_totals": {
                            "total_cost_usd": 0.02,
                            "llm_call_count": 1,
                            "search_tool_call_count": 1,
                            "embedding_call_count": 0,
                        },
                        "token_usage": {"total_tokens": 200},
                        "provider_model_usage": {"chutes": {"model-a": 1}},
                    },
                },
            },
        ],
    }


def test_dashboard_snapshot_reports_missing_store_as_empty(tmp_path: Path) -> None:
    snapshot = build_dashboard_snapshot(database_path=tmp_path / "missing.sqlite3")
    assert snapshot["schema"] == "slai-miner-dashboard-v1"
    assert snapshot["backend"]["benchmark_store"] == "empty"
    assert snapshot["benchmark"]["latest"] is None


def test_dashboard_snapshot_uses_persisted_benchmark_and_runtime_evidence(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_local_eval_report()), encoding="utf-8")
    database = tmp_path / "bench.sqlite3"

    with BenchmarkStore(database) as store:
        store.ingest_report(
            report,
            strategy="b3",
            artifact_version="b3",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
            slai_config={
                "selected_agents": ["reasoning"],
                "runtime_measurements": [
                    {
                        "agent": "reasoning",
                        "operation": "reason",
                        "elapsed_ms": 12.5,
                    }
                ],
            },
        )

    snapshot = build_dashboard_snapshot(database_path=database)
    assert snapshot["backend"]["benchmark_store"] == "available"
    assert snapshot["benchmark"]["latest"]["total_score"] == 1.4
    assert snapshot["slai"]["selected_agents"] == ["reasoning"]
    assert snapshot["slai"]["runtime_evidence"] == "recorded"
    assert snapshot["performance"]["token_usage"] == 300
    assert snapshot["performance"]["tool_calls"] == 3
    assert snapshot["performance"]["provider_models"] == ["chutes / model-a"]


def test_corrupt_benchmark_store_is_frontend_safe(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    database.write_bytes(b"not a sqlite database")
    snapshot = _benchmark_snapshot(database)
    assert snapshot["state"] == "unavailable"
    assert snapshot["latest"] is None
    assert snapshot["recent"] == []


def _dependency_state(
    *,
    slai_status: str = "ready",
    slai_revision_state: str = "matching",
    slai_clean: bool = True,
) -> dict:
    return {
        "slai": {
            "status": slai_status,
            "actual_commit": "slai-pin",
            "expected_commit": "slai-pin",
            "revision_state": slai_revision_state,
            "worktree_state": "clean" if slai_clean else "modified",
            "revision_matches": slai_revision_state == "matching",
            "clean": slai_clean,
            "pinned": slai_revision_state == "matching" and slai_clean,
        },
        "harnyx": {
            "status": "ready",
            "actual_commit": "harnyx-pin",
            "expected_commit": "harnyx-pin",
            "revision_state": "matching",
            "worktree_state": "clean",
            "revision_matches": True,
            "clean": True,
            "pinned": True,
        },
        "miner": {
            "status": "ready",
            "actual_commit": "miner-head",
            "clean": True,
        },
    }


def test_healthy_slai_without_runtime_use_does_not_degrade_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        dashboard_api,
        "dependency_status",
        lambda config: _dependency_state(slai_clean=True),
    )

    snapshot = build_dashboard_snapshot(database_path=tmp_path / "missing.sqlite3")

    assert snapshot["backend"]["status"] == "ready"
    assert snapshot["slai"]["status"] == "ready"
    assert snapshot["slai"]["revision_state"] == "matching"
    assert snapshot["slai"]["worktree_state"] == "clean"
    assert snapshot["slai"]["pinned"] is True
    assert snapshot["slai"]["runtime_evidence"] == "not_recorded"
    assert snapshot["slai"]["selected_agents"] == []
    assert snapshot["slai"]["runtime_measurements"] == []


def test_modified_slai_worktree_is_distinct_from_revision_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = _dependency_state(slai_clean=False)
    state["slai"]["status"] = "degraded"
    monkeypatch.setattr(
        dashboard_api,
        "dependency_status",
        lambda config: state,
    )

    snapshot = build_dashboard_snapshot(database_path=tmp_path / "missing.sqlite3")

    assert snapshot["backend"]["status"] == "degraded"
    assert snapshot["slai"]["status"] == "degraded"
    assert snapshot["slai"]["revision_state"] == "matching"
    assert snapshot["slai"]["worktree_state"] == "modified"
    assert snapshot["slai"]["runtime_evidence"] == "not_recorded"


def test_real_slai_revision_mismatch_degrades_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        dashboard_api,
        "dependency_status",
        lambda config: _dependency_state(
            slai_status="degraded",
            slai_revision_state="mismatch",
        ),
    )

    snapshot = build_dashboard_snapshot(database_path=tmp_path / "missing.sqlite3")

    assert snapshot["backend"]["status"] == "degraded"
    assert snapshot["slai"]["status"] == "degraded"
    assert snapshot["slai"]["revision_state"] == "mismatch"
