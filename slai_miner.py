"""Development CLI for SLAI-derived Harnyx SN67 artifacts.

No command in this module registers a wallet, submits an artifact, or spends TAO.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifact_builder import build_all, build_artifact
from benchmark_store import BenchmarkStore
from utils.config_loader import get_config_section, load_config
from utils.miner_errors import MinerError
from utils.miner_helpers import PROJECT_ROOT, git_head, require_external_repository, run_checked


def _commits() -> dict[str,str]:
    slai=require_external_repository("slai","src/agents/agent_factory.py"); harnyx=require_external_repository("harnyx","packages/miner-sdk/pyproject.toml")
    return {"miner":git_head(PROJECT_ROOT),"slai":git_head(slai),"harnyx":git_head(harnyx)}


def dependency_status() -> dict[str,Any]:
    config=load_config(); external=get_config_section("external",config=config); result={}
    for name,sentinel in (("slai","src/agents/agent_factory.py"),("harnyx","packages/miner-sdk/pyproject.toml")):
        root=require_external_repository(name,sentinel); expected=str((external.get(name) or {}).get("expected_commit","")); actual=git_head(root)
        result[name]={"path":str(root.relative_to(PROJECT_ROOT)),"expected_commit":expected,"actual_commit":actual,"pinned":bool(expected and expected==actual)}
    result["miner"]={"actual_commit":git_head(PROJECT_ROOT)}; return result


def _store() -> BenchmarkStore:
    project=get_config_section("project"); return BenchmarkStore(PROJECT_ROOT/str(project.get("results_database","benchmarks/harnyx/results/miner_benchmarks.sqlite3")))


def _output_dir(label: str) -> Path:
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); path=PROJECT_ROOT/"benchmarks/harnyx/results"/(stamp+"-"+label); path.mkdir(parents=True,exist_ok=False); return path


def _summary(stdout: str) -> dict[str,Any]:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try: value=json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(value,dict): return value
    raise MinerError("official Harnyx command did not emit a machine-readable JSON summary")


def local_eval(artifact: Path, *, strategy: str, batch_id: str|None=None, task_id: str|None=None, mode: str="vs-champion") -> dict[str,Any]:
    harnyx=require_external_repository("harnyx","miner/src/harnyx_miner/local_eval.py"); output=_output_dir(strategy+"-local-eval")
    command=["uv","run","--frozen","--package","harnyx-miner","harnyx-miner-local-eval","--agent-path",str(artifact.resolve()),"--mode",mode,"--output-dir",str(output)]
    if batch_id: command.extend(["--batch-id",batch_id])
    if task_id: command.extend(["--task-id",task_id])
    completed=run_checked(command,cwd=harnyx,timeout=None); summary=_summary(completed.stdout); report=Path(str(summary["json_report"])).resolve()
    with _store() as store: run_id=store.ingest_report(report,strategy=strategy,artifact_version=strategy,commits=_commits(),slai_config=get_config_section("slai"))
    return {"run_id":run_id,"report":str(report),"markdown_report":summary.get("markdown_report"),"stderr_tail":completed.stderr.strip()[-1500:]}


def local_benchmark(artifact: Path, *, strategy: str, suite: str, source_batch_id: str, sample_size: int|None=None, parallelism: int|None=None) -> dict[str,Any]:
    harnyx=require_external_repository("harnyx","miner/src/harnyx_miner/local_benchmark.py"); output=_output_dir(strategy+"-"+suite); settings=get_config_section("harnyx").get("local_benchmark") or {}
    command=["uv","run","--frozen","--package","harnyx-miner","harnyx-miner-local-benchmark","--suite",suite,"--agent-path",str(artifact.resolve()),"--source-batch-id",source_batch_id,"--query-execution-time-limit-seconds",str(settings.get("query_execution_time_limit_seconds",300)),"--output-dir",str(output)]
    if sample_size is not None: command.extend(["--sample-size",str(sample_size)])
    if parallelism is not None: command.extend(["--parallelism",str(parallelism)])
    completed=run_checked(command,cwd=harnyx,timeout=None); summary=_summary(completed.stdout); report=Path(str(summary["json_report"])).resolve()
    with _store() as store: run_id=store.ingest_report(report,strategy=strategy,artifact_version=strategy,commits=_commits(),slai_config=get_config_section("slai"))
    return {"run_id":run_id,"report":str(report),"summary":summary,"stderr_tail":completed.stderr.strip()[-1500:]}


def _parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Build and benchmark SLAI-derived Harnyx SN67 artifacts."); commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("status")
    build=commands.add_parser("build"); build.add_argument("profile",choices=["b0","b1","b2","b3","b4","all"]); build.add_argument("--official-validate",action="store_true"); build.add_argument("--disable",action="append",default=[],choices=["provider_routing","decomposition","retrieval","evidence_ranking","verification"])
    smoke=commands.add_parser("slai-smoke"); smoke.add_argument("--agent",action="append",default=[]); smoke.add_argument("--reason"); smoke.add_argument("--retrieve")
    evaluate=commands.add_parser("eval"); evaluate.add_argument("--artifact",required=True); evaluate.add_argument("--strategy",required=True); evaluate.add_argument("--batch-id"); evaluate.add_argument("--task-id"); evaluate.add_argument("--mode",choices=["vs-champion","target-only"],default="vs-champion")
    bench=commands.add_parser("benchmark"); bench.add_argument("--artifact",required=True); bench.add_argument("--strategy",required=True); bench.add_argument("--suite",required=True); bench.add_argument("--source-batch-id",required=True); bench.add_argument("--sample-size",type=int); bench.add_argument("--parallelism",type=int)
    runs=commands.add_parser("runs"); runs.add_argument("--limit",type=int,default=20); return parser


def main(argv: list[str]|None=None) -> int:
    parser=_parser(); args=parser.parse_args(argv)
    try:
        if args.command=="status": result=dependency_status()
        elif args.command=="build":
            if args.profile=="all":
                if args.disable: parser.error("--disable is valid only for one profile")
                result=[item.to_dict() for item in build_all(official_validate=args.official_validate)]
            else: result=build_artifact(args.profile,official_validate=args.official_validate,disabled_components=tuple(args.disable)).to_dict()
        elif args.command=="slai-smoke":
            from adapters.slai import SlaiRuntime
            agents=list(args.agent)
            if args.reason and "reasoning" not in agents: agents.append("reasoning")
            if args.retrieve and "knowledge" not in agents: agents.append("knowledge")
            with SlaiRuntime(agents) as runtime:
                result={"runtime":runtime.snapshot()}
                if args.reason: result["reasoning"]=runtime.reason(args.reason)
                if args.retrieve: result["retrieval"]=runtime.retrieve(args.retrieve)
                result["runtime"]=runtime.snapshot()
        elif args.command=="eval": result=local_eval(Path(args.artifact),strategy=args.strategy,batch_id=args.batch_id,task_id=args.task_id,mode=args.mode)
        elif args.command=="benchmark": result=local_benchmark(Path(args.artifact),strategy=args.strategy,suite=args.suite,source_batch_id=args.source_batch_id,sample_size=args.sample_size,parallelism=args.parallelism)
        else:
            with _store() as store:
                result=[{"run_id":r.run_id,"run_kind":r.run_kind,"strategy":r.strategy,"artifact_hash":r.artifact_hash,"score":r.score,"cost_usd":r.cost_usd,"median_runtime_ms":r.median_runtime_ms,"p95_runtime_ms":r.p95_runtime_ms,"error_rate":r.error_rate,"created_at":r.created_at} for r in store.latest_runs(limit=args.limit)]
        print(json.dumps(result,indent=2,sort_keys=True,default=str)); return 0
    except MinerError as exc:
        print(json.dumps(exc.to_dict(),indent=2,sort_keys=True)); return 2


if __name__=="__main__": raise SystemExit(main())
