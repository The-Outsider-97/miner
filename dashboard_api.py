"""Frontend-safe read-only snapshot of Miner benchmark and integration state."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_store import BenchmarkStore
from slai_miner import dependency_status
from utils.config_loader import get_config_section, load_config
from utils.miner_errors import MinerError
from utils.miner_helpers import PROJECT_ROOT, git_head

_COMPONENTS = (
    "provider_routing",
    "decomposition",
    "retrieval",
    "evidence_ranking",
    "verification",
)


def build_dashboard_snapshot() -> dict[str, Any]:
    """Return one normalized, frontend-safe dashboard document."""

    config = load_config()
    project = get_config_section("project", config=config)
    external = get_config_section("external", config=config)
    slai_config = get_config_section("slai", config=config)
    harnyx_config = get_config_section("harnyx", config=config)

    database_path = PROJECT_ROOT / str(
        project.get(
            "results_database",
            "benchmarks/harnyx/results/miner_benchmarks.sqlite3",
        )
    )
    benchmark = _benchmark_snapshot(database_path)
    latest = benchmark.get("latest")
    dependencies = _dependency_snapshot(external)
    selected_agents, measurements = _recorded_slai_runtime(latest)
    metadata = _report_metadata(latest)

    return {
        "schema": "slai-miner-dashboard-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": {
            "status": "ready",
            "benchmark_store": benchmark["state"],
            "data_source": "BenchmarkStore + Harnyx reports + artifact manifests",
            "message": benchmark.get("message"),
        },
        "artifact": _artifact_snapshot(latest),
        "slai": {
            "status": dependencies["slai"]["status"],
            "commit": dependencies["slai"].get("actual_commit"),
            "expected_commit": dependencies["slai"].get("expected_commit"),
            "pinned": dependencies["slai"].get("pinned", False),
            "selected_agents": selected_agents,
            "runtime_measurements": measurements,
            "runtime_evidence": (
                "recorded" if selected_agents or measurements else "not_recorded"
            ),
            "runtime_candidates": list(slai_config.get("runtime_candidates") or ()),
        },
        "harnyx": {
            "status": dependencies["harnyx"]["status"],
            "commit": dependencies["harnyx"].get("actual_commit"),
            "expected_commit": dependencies["harnyx"].get("expected_commit"),
            "pinned": dependencies["harnyx"].get("pinned", False),
            "sdk_version": str(
                (external.get("harnyx") or {}).get("sdk_version")
                or harnyx_config.get("sdk_version")
                or ""
            ),
        },
        "benchmark": {
            "latest": _frontend_run(latest),
            "recent": [_frontend_run(run) for run in benchmark.get("recent", ())],
        },
        "performance": _performance_snapshot(latest),
        "versions": {
            "miner_commit": _safe_miner_commit(),
            "slai_commit": dependencies["slai"].get("actual_commit"),
            "harnyx_commit": dependencies["harnyx"].get("actual_commit"),
            "dataset_version": metadata.get("dataset_version"),
            "scoring_version": metadata.get("scoring_version"),
            "suite_slug": metadata.get("suite_slug"),
            "batch_id": _value(latest, "batch_id"),
            "source_batch_id": _value(latest, "source_batch_id"),
        },
    }


def _benchmark_snapshot(database_path: Path) -> dict[str, Any]:
    if not database_path.exists():
        return {
            "state": "empty",
            "message": "No benchmark results available yet.",
            "latest": None,
            "recent": [],
        }

    try:
        with BenchmarkStore(database_path) as store:
            rows = store.connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            runs = [_decode_run(store, dict(row)) for row in rows]
    except sqlite3.Error as exc:
        return {
            "state": "unavailable",
            "message": f"BenchmarkStore could not be read: {exc}",
            "latest": None,
            "recent": [],
        }

    if not runs:
        return {
            "state": "empty",
            "message": "No benchmark results available yet.",
            "latest": None,
            "recent": [],
        }
    return {"state": "available", "message": None, "latest": runs[0], "recent": runs}


def _decode_run(store: BenchmarkStore, row: dict[str, Any]) -> dict[str, Any]:
    row["ablation"] = _json_object(row.pop("ablation_json", "{}"))
    row["slai_config"] = _json_object(row.pop("slai_config_json", "{}"))
    row["summary"] = _json_object(row.pop("raw_summary_json", "{}"))
    tasks = []
    for task in store.task_results(str(row["run_id"])):
        normalized = dict(task)
        normalized["provider_model"] = _json_value(
            normalized.pop("provider_model_json", "{}"),
            default={},
        )
        tasks.append(normalized)
    row["tasks"] = tasks
    return row


def _dependency_snapshot(external: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for name in ("slai", "harnyx"):
        settings = external.get(name) or {}
        output[name] = {
            "status": "unavailable",
            "expected_commit": str(settings.get("expected_commit") or ""),
            "actual_commit": None,
            "pinned": False,
        }
    try:
        live = dependency_status()
    except MinerError as exc:
        for item in output.values():
            item["detail"] = str(exc)
        return output
    for name in ("slai", "harnyx"):
        current = live.get(name) or {}
        output[name] = {
            "status": "ready" if current.get("actual_commit") else "unavailable",
            "expected_commit": current.get("expected_commit"),
            "actual_commit": current.get("actual_commit"),
            "pinned": bool(current.get("pinned")),
        }
    return output


def _artifact_snapshot(latest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    manifest = _latest_manifest(PROJECT_ROOT / "benchmarks/harnyx/manifests")
    if manifest is not None:
        strategy = (
            manifest.get("strategy")
            if isinstance(manifest.get("strategy"), Mapping)
            else {}
        )
        return {
            "profile": manifest.get("profile"),
            "version": manifest.get("profile"),
            "hash": manifest.get("sha256"),
            "size_bytes": manifest.get("size_bytes"),
            "validated": manifest.get("official_harnyx_validation"),
            "built_at": manifest.get("built_at"),
            "strategy": strategy,
            "enabled_components": [key for key in _COMPONENTS if strategy.get(key) is True],
            "disabled_components": list(
                _mapping(manifest.get("ablation")).get("disabled_components") or ()
            ),
        }
    if latest is None:
        return None
    return {
        "profile": latest.get("strategy"),
        "version": latest.get("artifact_version"),
        "hash": latest.get("artifact_hash"),
        "size_bytes": None,
        "validated": None,
        "built_at": None,
        "strategy": None,
        "enabled_components": [],
        "disabled_components": list(
            _mapping(latest.get("ablation")).get("disabled_components") or ()
        ),
    }


def _latest_manifest(root: Path) -> dict[str, Any] | None:
    if not root.exists():
        return None
    for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _performance_snapshot(latest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if latest is None:
        return None
    tasks = latest.get("tasks")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes, bytearray)):
        tasks = ()
    token_usage = 0
    tool_calls = 0
    providers: set[str] = set()
    for raw_task in tasks:
        if not isinstance(raw_task, Mapping):
            continue
        token_usage += _int_or_zero(raw_task.get("token_usage"))
        tool_calls += _int_or_zero(raw_task.get("tool_calls"))
        provider_model = raw_task.get("provider_model")
        if isinstance(provider_model, Mapping):
            providers.update(str(key) for key in provider_model if str(key).strip())
    return {
        "total_cost_usd": latest.get("total_cost_usd"),
        "token_usage": token_usage,
        "tool_calls": tool_calls,
        "provider_models": sorted(providers),
        "median_runtime_ms": latest.get("median_runtime_ms"),
        "p95_runtime_ms": latest.get("p95_runtime_ms"),
        "timeout_rate": latest.get("timeout_rate"),
        "error_rate": latest.get("error_rate"),
        "citation_failure_rate": latest.get("citation_failure_rate"),
        "structured_output_failure_rate": latest.get("structured_output_failure_rate"),
    }


def _recorded_slai_runtime(
    latest: Mapping[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    config = _mapping(latest.get("slai_config")) if latest is not None else {}
    raw_agents = config.get("selected_agents") or config.get("agents_used") or ()
    selected = (
        [str(agent) for agent in raw_agents]
        if isinstance(raw_agents, Sequence) and not isinstance(raw_agents, (str, bytes, bytearray))
        else []
    )
    raw_measurements = config.get("runtime_measurements") or ()
    measurements = (
        [dict(item) for item in raw_measurements if isinstance(item, Mapping)]
        if isinstance(raw_measurements, Sequence)
        and not isinstance(raw_measurements, (str, bytes, bytearray))
        else []
    )
    return selected, measurements


def _report_metadata(latest: Mapping[str, Any] | None) -> dict[str, Any]:
    if latest is None:
        return {}
    raw_path = latest.get("report_path")
    if not isinstance(raw_path, str) or not raw_path:
        return {}
    path = Path(raw_path)
    if not path.is_file():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, Mapping):
        return {}
    manifest = _mapping(_mapping(report.get("benchmark_metadata")).get("manifest"))
    if manifest:
        return {
            "dataset_version": manifest.get("dataset_version"),
            "scoring_version": manifest.get("scoring_version"),
            "suite_slug": manifest.get("suite_slug"),
        }
    batch = _mapping(report.get("batch_metadata"))
    return {
        "dataset_version": batch.get("data_version") or batch.get("dataset_version"),
        "scoring_version": batch.get("scoring_version"),
        "suite_slug": batch.get("suite_slug"),
    }


def _frontend_run(run: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    keys = (
        "run_id", "run_kind", "strategy", "artifact_hash", "artifact_version",
        "batch_id", "source_batch_id", "total_score", "comparison_score",
        "fast_score", "normal_score", "wins", "losses", "ties",
        "total_cost_usd", "median_runtime_ms", "p95_runtime_ms", "timeout_rate",
        "error_rate", "citation_failure_rate", "structured_output_failure_rate",
        "created_at",
    )
    payload = {key: run.get(key) for key in keys}
    payload["champion_selected"] = _bool_or_none(run.get("champion_selected"))
    return payload


def _safe_miner_commit() -> str | None:
    try:
        return git_head(PROJECT_ROOT)
    except MinerError:
        return None


def _json_object(raw: object) -> dict[str, Any]:
    value = _json_value(raw, default={})
    return dict(value) if isinstance(value, Mapping) else {}


def _json_value(raw: object, *, default: Any) -> Any:
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _value(mapping: object, key: str) -> Any:
    return mapping.get(key) if isinstance(mapping, Mapping) else None


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit frontend-safe Miner dashboard data.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    snapshot = build_dashboard_snapshot()
    print(
        json.dumps(snapshot, sort_keys=True, default=str)
        if args.json
        else json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
