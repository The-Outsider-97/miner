"""Persistent experiment ledger for official Harnyx evaluation reports.

BenchmarkStore owns Miner experiment analytics only. It is deliberately separate
from SLAI SharedMemory and agent memory. Official Harnyx JSON remains the scoring
source of truth; this module only normalizes it for comparison and observability.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import uuid

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils.miner_errors import BenchmarkExecutionError


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_id: str
    run_kind: str
    strategy: str
    artifact_hash: str
    score: float | None
    cost_usd: float | None
    median_runtime_ms: float | None
    p95_runtime_ms: float | None
    error_rate: float | None
    created_at: str


class BenchmarkStore:
    """SQLite-backed store for reproducible Miner experiments."""

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path).expanduser().resolve()
        self.read_only = bool(read_only)
        if self.read_only:
            if not self.path.is_file():
                raise BenchmarkExecutionError(
                    "BenchmarkStore database does not exist",
                    context={"path": str(self.path)},
                )
            self._connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, timeout=5.0
            )
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=5.0)

        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        if self.read_only:
            self._connection.execute("PRAGMA query_only=ON")
        else:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs(
                  run_id TEXT PRIMARY KEY, run_kind TEXT NOT NULL, report_path TEXT NOT NULL,
                  artifact_id TEXT, artifact_hash TEXT NOT NULL, artifact_version TEXT NOT NULL,
                  strategy TEXT NOT NULL, batch_id TEXT, source_batch_id TEXT,
                  total_score REAL, comparison_score REAL, fast_score REAL, normal_score REAL,
                  wins INTEGER, losses INTEGER, ties INTEGER, total_cost_usd REAL,
                  median_runtime_ms REAL, p95_runtime_ms REAL, timeout_rate REAL,
                  error_rate REAL, citation_failure_rate REAL, structured_output_failure_rate REAL,
                  champion_selected INTEGER, ablation_json TEXT NOT NULL, slai_config_json TEXT NOT NULL,
                  harnyx_commit TEXT NOT NULL, slai_commit TEXT NOT NULL, miner_commit TEXT NOT NULL,
                  raw_summary_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_results(
                  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                  task_id TEXT NOT NULL, query_mode TEXT NOT NULL, score REAL, runtime_ms REAL,
                  cost_usd REAL, tool_calls INTEGER, token_usage INTEGER,
                  provider_model_json TEXT NOT NULL, timeout INTEGER NOT NULL,
                  error_category TEXT, citation_failure INTEGER NOT NULL,
                  structured_output_failure INTEGER NOT NULL,
                  PRIMARY KEY(run_id, task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_strategy ON runs(strategy, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id, created_at DESC);
                """
            )

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise BenchmarkExecutionError(
                "BenchmarkStore was opened read-only",
                context={"path": str(self.path)},
            )

    def ingest_report(
        self,
        report_path: str | Path,
        *,
        strategy: str,
        artifact_version: str,
        commits: Mapping[str, str],
        ablation: Mapping[str, Any] | None = None,
        slai_config: Mapping[str, Any] | None = None,
    ) -> str:
        self._ensure_writable()
        path = Path(report_path).expanduser().resolve()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkExecutionError(
                "unable to read official Harnyx JSON report",
                context={"path": str(path)},
            ) from exc
        if not isinstance(report, Mapping):
            raise BenchmarkExecutionError("official Harnyx report root must be a JSON object")

        normalized = (
            _normalize_eval(report)
            if "local_result_summary" in report
            else _normalize_benchmark(report)
        )
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        run = {
            "run_id": run_id,
            "run_kind": normalized["kind"],
            "report_path": str(path),
            "artifact_id": normalized["artifact_id"],
            "artifact_hash": normalized["artifact_hash"],
            "artifact_version": artifact_version,
            "strategy": strategy,
            "batch_id": normalized["batch_id"],
            "source_batch_id": normalized["source_batch_id"],
            "total_score": normalized["total_score"],
            "comparison_score": normalized["comparison_score"],
            "fast_score": normalized["fast_score"],
            "normal_score": normalized["normal_score"],
            "wins": normalized["wins"],
            "losses": normalized["losses"],
            "ties": normalized["ties"],
            "total_cost_usd": normalized["cost"],
            "median_runtime_ms": normalized["median"],
            "p95_runtime_ms": normalized["p95"],
            "timeout_rate": normalized["timeout_rate"],
            "error_rate": normalized["error_rate"],
            "citation_failure_rate": normalized["citation_rate"],
            "structured_output_failure_rate": normalized["structured_rate"],
            "champion_selected": (
                None if normalized["champion"] is None else int(normalized["champion"])
            ),
            "ablation_json": _dump(ablation or {}),
            "slai_config_json": _dump(slai_config or {}),
            "harnyx_commit": str(commits.get("harnyx", "unknown")),
            "slai_commit": str(commits.get("slai", "unknown")),
            "miner_commit": str(commits.get("miner", "unknown")),
            "raw_summary_json": _dump(normalized["summary"]),
            "created_at": created_at,
        }
        tasks = [
            {
                "run_id": run_id,
                "task_id": item["task_id"],
                "query_mode": item["mode"],
                "score": item["score"],
                "runtime_ms": item["runtime"],
                "cost_usd": item["cost"],
                "tool_calls": item["calls"],
                "token_usage": item["tokens"],
                "provider_model_json": _dump(item["provider"]),
                "timeout": int(item["timeout"]),
                "error_category": item["error"],
                "citation_failure": int(item["citation"]),
                "structured_output_failure": int(item["structured"]),
            }
            for item in normalized["tasks"]
        ]

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO runs(
                  run_id,run_kind,report_path,artifact_id,artifact_hash,artifact_version,strategy,
                  batch_id,source_batch_id,total_score,comparison_score,fast_score,normal_score,
                  wins,losses,ties,total_cost_usd,median_runtime_ms,p95_runtime_ms,timeout_rate,
                  error_rate,citation_failure_rate,structured_output_failure_rate,champion_selected,
                  ablation_json,slai_config_json,harnyx_commit,slai_commit,miner_commit,
                  raw_summary_json,created_at
                ) VALUES(
                  :run_id,:run_kind,:report_path,:artifact_id,:artifact_hash,:artifact_version,:strategy,
                  :batch_id,:source_batch_id,:total_score,:comparison_score,:fast_score,:normal_score,
                  :wins,:losses,:ties,:total_cost_usd,:median_runtime_ms,:p95_runtime_ms,:timeout_rate,
                  :error_rate,:citation_failure_rate,:structured_output_failure_rate,:champion_selected,
                  :ablation_json,:slai_config_json,:harnyx_commit,:slai_commit,:miner_commit,
                  :raw_summary_json,:created_at
                )
                """,
                run,
            )
            self._connection.executemany(
                """
                INSERT INTO task_results(
                  run_id,task_id,query_mode,score,runtime_ms,cost_usd,tool_calls,token_usage,
                  provider_model_json,timeout,error_category,citation_failure,structured_output_failure
                ) VALUES(
                  :run_id,:task_id,:query_mode,:score,:runtime_ms,:cost_usd,:tool_calls,:token_usage,
                  :provider_model_json,:timeout,:error_category,:citation_failure,:structured_output_failure
                )
                """,
                tasks,
            )
        return run_id

    def latest_runs(self, *, limit: int = 20) -> list[StoredRun]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self._connection.execute(
            """SELECT run_id,run_kind,strategy,artifact_hash,total_score,total_cost_usd,
                      median_runtime_ms,p95_runtime_ms,error_rate,created_at
               FROM runs ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            StoredRun(
                row["run_id"], row["run_kind"], row["strategy"], row["artifact_hash"],
                row["total_score"], row["total_cost_usd"], row["median_runtime_ms"],
                row["p95_runtime_ms"], row["error_rate"], row["created_at"],
            )
            for row in rows
        ]

    def recent_run_details(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return normalized run rows plus tasks using two bounded queries."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self._connection.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return []
        run_ids = [str(row["run_id"]) for row in rows]
        placeholders = ",".join("?" for _ in run_ids)
        task_rows = self._connection.execute(
            f"SELECT * FROM task_results WHERE run_id IN ({placeholders}) ORDER BY run_id,task_id",
            run_ids,
        ).fetchall()
        by_run: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
        for row in task_rows:
            task = dict(row)
            task["provider_model"] = _load_json(
                task.pop("provider_model_json"), "task_results.provider_model_json"
            )
            by_run[str(row["run_id"])].append(task)

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["ablation"] = _load_json(item.pop("ablation_json"), "runs.ablation_json")
            item["slai_config"] = _load_json(item.pop("slai_config_json"), "runs.slai_config_json")
            item["summary"] = _load_json(item.pop("raw_summary_json"), "runs.raw_summary_json")
            item["tasks"] = by_run[str(row["run_id"])]
            result.append(item)
        return result

    def task_results(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM task_results WHERE run_id=? ORDER BY task_id", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "BenchmarkStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False


def _normalize_eval(report: Mapping[str, Any]) -> dict[str, Any]:
    identifiers = _map(report.get("identifiers"))
    target_artifact = _map(_map(report.get("artifacts")).get("target"))
    summary = _map(report.get("local_result_summary"))
    head = _map(summary.get("head_to_head"))
    selection = _map(summary.get("local_champion_selection"))
    modes = _mode_map(report)
    tasks = []
    for raw in _seq(report.get("tasks")):
        row = _map(raw)
        target = _map(row.get("target"))
        task_id = str(row.get("task_id") or "")
        if task_id and target:
            tasks.append(_task_from_eval(task_id, modes.get(task_id, "unknown"), target))

    scores = [task["score"] for task in tasks if task["score"] is not None]
    fast = [task["score"] for task in tasks if task["mode"] == "fast" and task["score"] is not None]
    normal = [task["score"] for task in tasks if task["mode"] == "normal" and task["score"] is not None]
    target_leaderboard = next(
        (_map(item) for item in _seq(summary.get("leaderboard")) if _map(item).get("label") == "target"),
        {},
    )
    return _aggregate({
        "kind": "local_eval",
        "batch_id": str(identifiers.get("batch_id") or "") or None,
        "source_batch_id": None,
        "artifact_id": str(target_artifact.get("artifact_id") or identifiers.get("target_artifact_id") or ""),
        "artifact_hash": str(target_artifact.get("sha256") or target_artifact.get("content_hash") or ""),
        "total_score": _float(target_leaderboard.get("total_score")) if target_leaderboard else (sum(scores) if scores else None),
        "comparison_score": _float(target_leaderboard.get("avg_score")) if target_leaderboard else _mean(scores),
        "fast_score": _mean(fast),
        "normal_score": _mean(normal),
        "wins": _int(head.get("wins")),
        "losses": _int(head.get("losses")),
        "ties": _int(head.get("ties")),
        "champion": (
            selection.get("selected_label") == "target"
            if selection.get("selected_label") is not None else None
        ),
        "summary": summary,
        "tasks": tasks,
    })


def _normalize_benchmark(report: Mapping[str, Any]) -> dict[str, Any]:
    identifiers = _map(report.get("identifiers"))
    target = _map(_map(report.get("artifacts")).get("target"))
    summary = _map(report.get("summary"))
    tasks = []
    for raw in _seq(report.get("items")):
        row = _map(raw)
        task_id = str(row.get("task_id") or "")
        if not task_id:
            continue
        invocation = _map(row.get("invocation"))
        error = _map(invocation.get("error")) or _map(row.get("error"))
        tasks.append(_task(
            task_id,
            "benchmark",
            row.get("score"),
            invocation.get("elapsed_ms"),
            _map(invocation.get("cost_totals")),
            _map(invocation.get("token_usage")),
            {},
            error,
        ))
    score = _float(summary.get("mean_total_score"))
    return _aggregate({
        "kind": "local_benchmark",
        "batch_id": None,
        "source_batch_id": str(identifiers.get("source_batch_id") or "") or None,
        "artifact_id": str(target.get("artifact_id") or identifiers.get("target_artifact_id") or ""),
        "artifact_hash": str(target.get("sha256") or target.get("content_hash") or ""),
        "total_score": score,
        "comparison_score": None,
        "fast_score": None,
        "normal_score": None,
        "wins": None,
        "losses": None,
        "ties": None,
        "champion": None,
        "summary": summary,
        "tasks": tasks,
    })


def _task_from_eval(task_id: str, mode: str, target: Mapping[str, Any]) -> dict[str, Any]:
    usage = _map(target.get("cost_and_usage"))
    return _task(
        task_id, mode, target.get("score"), target.get("elapsed_ms"),
        _map(usage.get("cost_totals")), _map(usage.get("token_usage")),
        usage.get("provider_model_usage") or {}, _map(target.get("error")),
    )


def _task(
    task_id: str,
    mode: str,
    score: Any,
    runtime: Any,
    costs: Mapping[str, Any],
    tokens: Mapping[str, Any],
    provider: Any,
    error: Mapping[str, Any],
) -> dict[str, Any]:
    error_text = _dump(error).lower()
    error_code = str(error.get("code") or "").strip() or None
    return {
        "task_id": task_id,
        "mode": mode,
        "score": _float(score),
        "runtime": _float(runtime),
        "cost": _float(costs.get("total_cost_usd")),
        "calls": _sum(costs, "llm_call_count", "search_tool_call_count", "embedding_call_count"),
        "tokens": _int(tokens.get("total_tokens")),
        "provider": provider,
        "timeout": "timeout" in error_text or "deadline" in error_text,
        "error": error_code,
        "citation": "citation" in error_text,
        "structured": any(term in error_text for term in ("structured", "schema", "response output", "output_schema")),
    }


def _aggregate(data: dict[str, Any]) -> dict[str, Any]:
    tasks = data["tasks"]
    runtimes = [task["runtime"] for task in tasks if task["runtime"] is not None]
    costs = [task["cost"] for task in tasks if task["cost"] is not None]
    count = len(tasks)
    data.update({
        "cost": sum(costs) if costs else None,
        "median": statistics.median(runtimes) if runtimes else None,
        "p95": _p95(runtimes),
        "timeout_rate": sum(task["timeout"] for task in tasks) / count if count else None,
        "error_rate": sum(task["error"] is not None for task in tasks) / count if count else None,
        "citation_rate": sum(task["citation"] for task in tasks) / count if count else None,
        "structured_rate": sum(task["structured"] for task in tasks) / count if count else None,
    })
    return data


def _mode_map(report: Mapping[str, Any]) -> dict[str, str]:
    batch = _map(_map(report.get("batch_metadata")).get("batch"))
    output: dict[str, str] = {}
    for raw in _seq(batch.get("tasks")):
        task = _map(raw)
        task_id = str(task.get("task_id") or task.get("id") or "")
        if task_id:
            output[task_id] = "fast" if _map(task.get("query")).get("fast") is True else "normal"
    return output


def _p95(values: Sequence[float]) -> float | None:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sum(mapping: Mapping[str, Any], *keys: str) -> int | None:
    values = [_int(mapping.get(key)) for key in keys]
    found = [value for value in values if value is not None]
    return sum(found) if found else None


def _load_json(raw: object, field: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise BenchmarkExecutionError(
            "stored BenchmarkStore JSON field is not text",
            context={"field": field, "actual_type": type(raw).__name__},
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BenchmarkExecutionError(
            "stored BenchmarkStore JSON is malformed", context={"field": field}
        ) from exc
    if not isinstance(value, Mapping):
        raise BenchmarkExecutionError(
            "stored BenchmarkStore JSON field must be an object",
            context={"field": field, "actual_type": type(value).__name__},
        )
    return dict(value)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
