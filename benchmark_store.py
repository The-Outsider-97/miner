"""Persistent experiment ledger for official Harnyx evaluation reports.

The database stores Miner benchmark analytics only. It is deliberately separate
from SLAI SharedMemory, KnowledgeMemory, LanguageMemory, and agent state. Harnyx
JSON remains the scoring source of truth; this module only normalizes it.
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

from utils.miner_errors import BenchmarkExecutionError


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

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
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
                """
            )

    def ingest_report(
        self,
        report_path: str | Path,
        *, strategy: str,
        artifact_version: str,
        commits: Mapping[str, str],
        ablation: Mapping[str, Any] | None = None,
        slai_config: Mapping[str, Any] | None = None,
    ) -> str:
        path = Path(report_path).expanduser().resolve()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkExecutionError("unable to read official Harnyx JSON report", context={"path": str(path)}) from exc
        if not isinstance(report, Mapping):
            raise BenchmarkExecutionError("official Harnyx report root must be a JSON object")
        normalized = _normalize_eval(report) if "local_result_summary" in report else _normalize_benchmark(report)
        run_id = normalized["run_id"] or str(uuid.uuid4())
        created = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO runs VALUES(
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, normalized["kind"], str(path), normalized["artifact_id"], normalized["artifact_hash"],
                    artifact_version, strategy, normalized["batch_id"], normalized["source_batch_id"],
                    normalized["total_score"], normalized["comparison_score"], normalized["fast_score"],
                    normalized["normal_score"], normalized["wins"], normalized["losses"], normalized["ties"],
                    normalized["cost"], normalized["median"], normalized["p95"], normalized["timeout_rate"],
                    normalized["error_rate"], normalized["citation_rate"], normalized["structured_rate"],
                    None if normalized["champion"] is None else int(normalized["champion"]),
                    _dump(ablation or {}), _dump(slai_config or {}), str(commits.get("harnyx", "unknown")),
                    str(commits.get("slai", "unknown")), str(commits.get("miner", "unknown")),
                    _dump(normalized["summary"]), created,
                ),
            )
            self.connection.execute("DELETE FROM task_results WHERE run_id=?", (run_id,))
            self.connection.executemany(
                "INSERT INTO task_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (run_id, t["task_id"], t["mode"], t["score"], t["runtime"], t["cost"], t["calls"],
                     t["tokens"], _dump(t["provider"]), int(t["timeout"]), t["error"],
                     int(t["citation"]), int(t["structured"]))
                    for t in normalized["tasks"]
                ],
            )
        return run_id

    def latest_runs(self, *, limit: int = 20) -> list[StoredRun]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self.connection.execute(
            "SELECT run_id,run_kind,strategy,artifact_hash,total_score,total_cost_usd,median_runtime_ms,p95_runtime_ms,error_rate,created_at FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [StoredRun(row["run_id"], row["run_kind"], row["strategy"], row["artifact_hash"], row["total_score"], row["total_cost_usd"], row["median_runtime_ms"], row["p95_runtime_ms"], row["error_rate"], row["created_at"]) for row in rows]

    def task_results(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM task_results WHERE run_id=? ORDER BY task_id", (run_id,)).fetchall()]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "BenchmarkStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False


def _normalize_eval(report: Mapping[str, Any]) -> dict[str, Any]:
    identifiers = _map(report.get("identifiers")); artifacts = _map(report.get("artifacts")); target_artifact = _map(artifacts.get("target"))
    summary = _map(report.get("local_result_summary")); head = _map(summary.get("head_to_head")); selection = _map(summary.get("local_champion_selection"))
    mode_map = _mode_map(report); tasks = []
    for item in _seq(report.get("tasks")):
        row = _map(item); target = _map(row.get("target")); task_id = str(row.get("task_id") or "")
        if task_id and target:
            tasks.append(_task_from_eval(task_id, mode_map.get(task_id, "unknown"), target))
    scores = [t["score"] for t in tasks if t["score"] is not None]
    fast = [t["score"] for t in tasks if t["mode"] == "fast" and t["score"] is not None]
    normal = [t["score"] for t in tasks if t["mode"] == "normal" and t["score"] is not None]
    return _aggregate({
        "kind":"local_eval", "run_id":str(identifiers.get("batch_id") or ""), "batch_id":str(identifiers.get("batch_id") or ""), "source_batch_id":None,
        "artifact_id":str(target_artifact.get("artifact_id") or identifiers.get("target_artifact_id") or ""),
        "artifact_hash":str(target_artifact.get("sha256") or target_artifact.get("content_hash") or ""),
        "total_score":sum(scores) if scores else None, "comparison_score":_mean(scores), "fast_score":_mean(fast), "normal_score":_mean(normal),
        "wins":_int(head.get("wins")), "losses":_int(head.get("losses")), "ties":_int(head.get("ties")),
        "champion": selection.get("selected_label") == "target" if selection.get("selected_label") is not None else None,
        "summary":summary, "tasks":tasks,
    })


def _normalize_benchmark(report: Mapping[str, Any]) -> dict[str, Any]:
    identifiers = _map(report.get("identifiers")); artifacts = _map(report.get("artifacts")); target = _map(artifacts.get("target")); summary = _map(report.get("summary")); tasks=[]
    for item in _seq(report.get("items")):
        row=_map(item); task_id=str(row.get("task_id") or ""); invocation=_map(row.get("invocation")); error=_map(row.get("error"))
        if not task_id: continue
        if invocation:
            costs=_map(invocation.get("cost_totals")); tokens=_map(invocation.get("token_usage")); error=_map(invocation.get("error")) or error
            tasks.append(_task(task_id,"benchmark",row.get("score"),invocation.get("elapsed_ms"),costs,tokens,{},error))
        else:
            tasks.append(_task(task_id,"benchmark",row.get("score"),None,{}, {}, {}, error))
    score=_float(summary.get("mean_total_score"))
    return _aggregate({"kind":"local_benchmark","run_id":str(identifiers.get("run_id") or ""),"batch_id":None,"source_batch_id":str(identifiers.get("source_batch_id") or ""),
        "artifact_id":str(target.get("artifact_id") or identifiers.get("target_artifact_id") or ""),"artifact_hash":str(target.get("sha256") or target.get("content_hash") or ""),
        "total_score":score,"comparison_score":score,"fast_score":None,"normal_score":None,"wins":None,"losses":None,"ties":None,"champion":None,"summary":summary,"tasks":tasks})


def _task_from_eval(task_id: str, mode: str, target: Mapping[str, Any]) -> dict[str, Any]:
    usage=_map(target.get("cost_and_usage")); return _task(task_id, mode, target.get("score"), target.get("elapsed_ms"), _map(usage.get("cost_totals")), _map(usage.get("token_usage")), usage.get("provider_model_usage") or {}, _map(target.get("error")))


def _task(task_id: str, mode: str, score: Any, runtime: Any, costs: Mapping[str, Any], tokens: Mapping[str, Any], provider: Any, error: Mapping[str, Any]) -> dict[str, Any]:
    text=_dump(error).lower(); return {"task_id":task_id,"mode":mode,"score":_float(score),"runtime":_float(runtime),"cost":_float(costs.get("total_cost_usd")),
        "calls":_sum(costs,"llm_call_count","search_tool_call_count","embedding_call_count"),"tokens":_int(tokens.get("total_tokens")),"provider":provider,
        "timeout":("timeout" in text or "deadline" in text),"error":str(error.get("code")) if error.get("code") not in (None,"") else None,
        "citation":"citation" in text,"structured":any(term in text for term in ("structured","schema","output"))}


def _aggregate(data: dict[str, Any]) -> dict[str, Any]:
    tasks=data["tasks"]; runtimes=[t["runtime"] for t in tasks if t["runtime"] is not None]; costs=[t["cost"] for t in tasks if t["cost"] is not None]; n=len(tasks)
    data.update({"cost":sum(costs) if costs else None,"median":statistics.median(runtimes) if runtimes else None,"p95":_p95(runtimes),
        "timeout_rate":sum(t["timeout"] for t in tasks)/n if n else None,"error_rate":sum(t["error"] is not None for t in tasks)/n if n else None,
        "citation_rate":sum(t["citation"] for t in tasks)/n if n else None,"structured_rate":sum(t["structured"] for t in tasks)/n if n else None})
    return data


def _mode_map(report: Mapping[str, Any]) -> dict[str,str]:
    batch=_map(_map(report.get("batch_metadata")).get("batch")); out={}
    for item in _seq(batch.get("tasks")):
        task=_map(item); query=_map(task.get("query")); task_id=str(task.get("task_id") or task.get("id") or "")
        if task_id: out[task_id]="fast" if query.get("fast") is True else "normal"
    return out


def _p95(values: Sequence[float]) -> float | None:
    if not values: return None
    ordered=sorted(v for v in values if math.isfinite(v)); return ordered[max(0, math.ceil(len(ordered)*0.95)-1)] if ordered else None

def _map(value: Any) -> Mapping[str,Any]: return value if isinstance(value, Mapping) else {}
def _seq(value: Any) -> Sequence[Any]: return value if isinstance(value,(list,tuple)) else ()
def _mean(values: Sequence[float]) -> float | None: return sum(values)/len(values) if values else None
def _float(value: Any) -> float | None:
    try: number=float(value)
    except (TypeError,ValueError): return None
    return number if math.isfinite(number) else None
def _int(value: Any) -> int | None:
    try: return int(value) if value is not None else None
    except (TypeError,ValueError): return None
def _sum(mapping: Mapping[str,Any], *keys: str) -> int | None:
    values=[_int(mapping.get(key)) for key in keys]; found=[v for v in values if v is not None]; return sum(found) if found else None
def _dump(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"), default=str)
