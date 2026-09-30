from __future__ import annotations

import json
from pathlib import Path

from benchmark_store import BenchmarkStore
from dashboard_api import _benchmark_snapshot, build_dashboard_snapshot


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
