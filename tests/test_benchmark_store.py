import json
from pathlib import Path

from benchmark_store import BenchmarkStore


def _report():
    return {"batch_metadata":{"batch":{"tasks":[{"task_id":"fast","query":{"fast":True}},{"task_id":"normal","query":{"fast":False}}]}},"identifiers":{"batch_id":"batch-1","target_artifact_id":"artifact-1"},"artifacts":{"target":{"artifact_id":"artifact-1","sha256":"a"*64}},"local_result_summary":{"head_to_head":{"wins":1,"losses":0,"ties":1},"local_champion_selection":{"selected_label":"target"},"leaderboard":[]},"tasks":[
      {"task_id":"fast","target":{"score":0.8,"elapsed_ms":100.0,"error":None,"cost_and_usage":{"cost_totals":{"total_cost_usd":0.01,"llm_call_count":1,"search_tool_call_count":0,"embedding_call_count":0},"token_usage":{"total_tokens":100},"provider_model_usage":{"chutes":{"m":1}}}}},
      {"task_id":"normal","target":{"score":0.6,"elapsed_ms":300.0,"error":{"code":"citation_validation_failed"},"cost_and_usage":{"cost_totals":{"total_cost_usd":0.02,"llm_call_count":1,"search_tool_call_count":1,"embedding_call_count":0},"token_usage":{"total_tokens":200},"provider_model_usage":{"chutes":{"m":1}}}}}
    ]}


def test_store_ingests_current_local_eval_shape(tmp_path: Path):
    path=tmp_path/"report.json"; path.write_text(json.dumps(_report()),encoding="utf-8")
    with BenchmarkStore(tmp_path/"bench.sqlite3") as store:
        run_id=store.ingest_report(path,strategy="b3",artifact_version="b3",commits={"miner":"m","slai":"s","harnyx":"h"})
        run=store.latest_runs(limit=1)[0]; tasks=store.task_results(run_id)
    assert run.score==1.4
    assert run.cost_usd==0.03
    assert run.median_runtime_ms==200.0
    assert run.p95_runtime_ms==300.0
    assert run.error_rate==0.5
    assert {row["query_mode"] for row in tasks}=={"fast","normal"}
    assert next(row for row in tasks if row["query_mode"]=="normal")["citation_failure"]==1
