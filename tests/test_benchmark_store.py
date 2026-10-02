import json
from pathlib import Path

import pytest

from miner.benchmark_store import BenchmarkStore
from miner.utils.miner_errors import BenchmarkExecutionError


def _report():
    return {
        "batch_metadata": {
            "batch": {
                "tasks": [
                    {"task_id": "fast", "query": {"fast": True}},
                    {"task_id": "normal", "query": {"fast": False}},
                ]
            }
        },
        "identifiers": {"batch_id": "batch-1", "target_artifact_id": "artifact-1"},
        "artifacts": {"target": {"artifact_id": "artifact-1", "sha256": "a" * 64}},
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
                        "provider_model_usage": {"chutes": {"m": 1}},
                    },
                },
            },
            {
                "task_id": "normal",
                "target": {
                    "score": 0.6,
                    "elapsed_ms": 300.0,
                    "error": {"code": "miner_response_invalid", "message": "citation validation failed"},
                    "cost_and_usage": {
                        "cost_totals": {
                            "total_cost_usd": 0.02,
                            "llm_call_count": 1,
                            "search_tool_call_count": 1,
                            "embedding_call_count": 0,
                        },
                        "token_usage": {"total_tokens": 200},
                        "provider_model_usage": {"chutes": {"m": 1}},
                    },
                },
            },
        ],
    }


def _benchmark_report():
    return {
        "benchmark_metadata": {
            "manifest": {
                "suite_slug": "suite",
                "dataset_version": "v1",
                "scoring_version": "correctness-v1",
            }
        },
        "identifiers": {
            "source_batch_id": "source-batch",
            "target_artifact_id": "artifact-b",
        },
        "artifacts": {
            "target": {
                "artifact_id": "artifact-b",
                "sha256": "b" * 64,
            }
        },
        "summary": {
            "item_count": 1,
            "completed_item_count": 1,
            "failed_item_count": 0,
            "mean_total_score": 0.75,
            "error_count": 0,
        },
        "items": [
            {
                "task_id": "bench-1",
                "score": 0.75,
                "error": None,
                "invocation": {
                    "elapsed_ms": 250.0,
                    "error": None,
                    "cost_totals": {
                        "total_cost_usd": 0.015,
                        "llm_call_count": 1,
                        "search_tool_call_count": 0,
                        "embedding_call_count": 0,
                    },
                    "token_usage": {"total_tokens": 150},
                },
            }
        ],
    }


def test_store_ingests_current_local_eval_shape(tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    with BenchmarkStore(tmp_path / "bench.sqlite3") as store:
        run_id = store.ingest_report(
            path,
            strategy="b3",
            artifact_version="b3",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
        )
        run = store.latest_runs(limit=1)[0]
        tasks = store.task_results(run_id)
    assert run.score == 1.4
    assert run.cost_usd == 0.03
    assert run.median_runtime_ms == 200.0
    assert run.p95_runtime_ms == 300.0
    assert run.error_rate == 0.5
    assert {row["query_mode"] for row in tasks} == {"fast", "normal"}
    normal = next(row for row in tasks if row["query_mode"] == "normal")
    assert normal["citation_failure"] == 1


def test_same_harnyx_batch_can_store_multiple_candidate_runs(tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    with BenchmarkStore(tmp_path / "bench.sqlite3") as store:
        first = store.ingest_report(
            path,
            strategy="b0",
            artifact_version="b0",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
        )
        second = store.ingest_report(
            path,
            strategy="b3",
            artifact_version="b3",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
            ablation={"disabled_components": []},
        )
        runs = store.latest_runs(limit=10)
    assert first != second
    assert len(runs) == 2
    assert {run.strategy for run in runs} == {"b0", "b3"}


def test_read_only_store_returns_normalized_run_details(tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    database = tmp_path / "bench.sqlite3"
    with BenchmarkStore(database) as store:
        run_id = store.ingest_report(
            path,
            strategy="b3",
            artifact_version="b3",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
            ablation={"disabled_components": ["verification"]},
        )

    with BenchmarkStore(database, read_only=True) as store:
        details = store.recent_run_details(limit=5)
        assert details[0]["run_id"] == run_id
        assert details[0]["ablation"]["disabled_components"] == ["verification"]
        assert details[0]["tasks"][0]["provider_model"] == {"chutes": {"m": 1}}
        with pytest.raises(BenchmarkExecutionError):
            store.ingest_report(
                path,
                strategy="b3",
                artifact_version="b3",
                commits={"miner": "m", "slai": "s", "harnyx": "h"},
            )


def test_local_benchmark_score_is_not_mislabeled_as_pairwise_comparison(tmp_path: Path):
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(_benchmark_report()), encoding="utf-8")
    database = tmp_path / "bench.sqlite3"
    with BenchmarkStore(database) as store:
        store.ingest_report(
            path,
            strategy="b3",
            artifact_version="b3",
            commits={"miner": "m", "slai": "s", "harnyx": "h"},
        )
        details = store.recent_run_details(limit=1)[0]
    assert details["run_kind"] == "local_benchmark"
    assert details["total_score"] == 0.75
    assert details["comparison_score"] is None
