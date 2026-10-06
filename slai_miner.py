"""Development CLI for SLAI-derived Harnyx SN67 artifacts.

No command in this module registers a wallet, submits an artifact, or spends TAO.
"""

from __future__ import annotations

import argparse
import json
import uuid
import sys

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Support the documented direct invocation from the repository root:
#     uv run python slai_miner.py status
#
# The repository directory itself is the package root. When this file is run
# directly, Python otherwise has no package context and relative imports fail.
if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = package_root.name

from .artifact_builder import build_all, build_artifact # type: ignore
from .benchmark_store import BenchmarkStore # type: ignore
from .utils.config_loader import get_config_section # type: ignore
from .utils.miner_errors import BenchmarkExecutionError, MinerConfigurationError, MinerError # type: ignore
from .utils.miner_helpers import PROJECT_ROOT, require_external_repository, run_checked # type: ignore
from .utils.repository_state import benchmark_database_path, dependency_status, repository_commits # type: ignore

_ARTIFACT_COMPONENTS = (
    "provider_routing",
    "decomposition",
    "retrieval",
    "evidence_ranking",
    "verification",
)


def _store() -> BenchmarkStore:
    return BenchmarkStore(benchmark_database_path())


def _output_dir(label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    path = PROJECT_ROOT / "benchmarks/harnyx/results" / f"{stamp}-{suffix}-{label}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _summary(stdout: str) -> dict[str, Any]:
    payload = stdout.strip()
    if payload:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value

    # Current Harnyx writes one compact JSON object to stdout. This fallback also
    # tolerates diagnostic lines or future pretty-printing without parsing stderr.
    starts = [index for index, char in enumerate(stdout) if char == "{"]
    for start in reversed(starts):
        candidate = stdout[start:].strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise BenchmarkExecutionError("official Harnyx command did not emit a machine-readable JSON summary")


def _harnyx_command_settings(name: str) -> Mapping[str, Any]:
    harnyx = get_config_section("harnyx")
    settings = harnyx.get(name) or {}
    if not isinstance(settings, Mapping):
        raise MinerConfigurationError(
            f"harnyx.{name} must be a mapping",
            context={"actual_type": type(settings).__name__},
        )
    return settings


def _required_text_setting(settings: Mapping[str, Any], key: str, *, section: str) -> str:
    value = str(settings.get(key) or "").strip()
    if not value:
        raise MinerConfigurationError(f"{section}.{key} must be configured")
    return value


def _report_path(summary: Mapping[str, Any], *, key: str, output_dir: Path) -> Path:
    raw = summary.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise BenchmarkExecutionError(
            "official Harnyx summary is missing the report path",
            context={"field": key},
        )
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (output_dir / candidate).resolve()
    output = output_dir.resolve()
    if path != output and output not in path.parents:
        raise BenchmarkExecutionError(
            "official Harnyx report path escaped the requested output directory",
            context={"field": key, "path": str(path), "output_dir": str(output)},
        )
    if not path.is_file():
        raise BenchmarkExecutionError(
            "official Harnyx report file does not exist",
            context={"field": key, "path": str(path)},
        )
    return path


def local_eval(
    artifact: Path,
    *,
    strategy: str,
    batch_id: str | None = None,
    task_id: str | None = None,
    mode: str | None = None,
    disabled_components: tuple[str, ...] = (),
) -> dict[str, Any]:
    harnyx = require_external_repository("harnyx", "miner/src/harnyx_miner/local_eval.py")
    settings = _harnyx_command_settings("local_eval")
    executable = _required_text_setting(settings, "executable", section="harnyx.local_eval")
    selected_mode = mode or _required_text_setting(
        settings,
        "default_mode",
        section="harnyx.local_eval",
    )
    if selected_mode not in {"vs-champion", "target-only"}:
        raise MinerConfigurationError(
            "harnyx.local_eval.default_mode is unsupported",
            context={"mode": selected_mode},
        )

    output = _output_dir(f"{strategy}-local-eval")
    command = [
        "uv",
        "run",
        "--frozen",
        "--package",
        "harnyx-miner",
        executable,
        "--agent-path",
        str(artifact.resolve()),
        "--mode",
        selected_mode,
        "--output-dir",
        str(output),
    ]
    if batch_id:
        command.extend(["--batch-id", batch_id])
    if task_id:
        command.extend(["--task-id", task_id])

    completed = run_checked(command, cwd=harnyx, timeout=None)
    summary = _summary(completed.stdout)
    report = _report_path(summary, key="json_report", output_dir=output)
    run_id: Any | None = None
    with _store() as store:
        run_id = store.ingest_report(
            report,
            strategy=strategy,
            artifact_version=strategy,
            commits=repository_commits(),
            ablation={"disabled_components": list(disabled_components)},
            slai_config=get_config_section("slai"),
        )
    return {
        "run_id": run_id,
        "report": str(report),
        "markdown_report": summary.get("markdown_report"),
        "stderr_tail": completed.stderr.strip()[-1500:],
    }


def local_benchmark(
    artifact: Path,
    *,
    strategy: str,
    suite: str,
    source_batch_id: str,
    sample_size: int | None = None,
    parallelism: int | None = None,
    disabled_components: tuple[str, ...] = (),
) -> dict[str, Any]:
    harnyx = require_external_repository(
        "harnyx",
        "miner/src/harnyx_miner/local_benchmark.py",
    )
    settings = _harnyx_command_settings("local_benchmark")
    executable = _required_text_setting(
        settings,
        "executable",
        section="harnyx.local_benchmark",
    )
    try:
        query_limit = float(settings["query_execution_time_limit_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MinerConfigurationError(
            "harnyx.local_benchmark.query_execution_time_limit_seconds must be numeric"
        ) from exc
    if query_limit <= 0:
        raise MinerConfigurationError(
            "harnyx.local_benchmark.query_execution_time_limit_seconds must be > 0"
        )

    output = _output_dir(f"{strategy}-{suite}")
    command = [
        "uv",
        "run",
        "--frozen",
        "--package",
        "harnyx-miner",
        executable,
        "--suite",
        suite,
        "--agent-path",
        str(artifact.resolve()),
        "--source-batch-id",
        source_batch_id,
        "--query-execution-time-limit-seconds",
        str(query_limit),
        "--output-dir",
        str(output),
    ]
    if sample_size is not None:
        command.extend(["--sample-size", str(sample_size)])
    if parallelism is not None:
        command.extend(["--parallelism", str(parallelism)])

    completed = run_checked(command, cwd=harnyx, timeout=None)
    summary = _summary(completed.stdout)
    report = _report_path(summary, key="json_report", output_dir=output)
    run_id: Any | None = None
    with _store() as store:
        run_id = store.ingest_report(
            report,
            strategy=strategy,
            artifact_version=strategy,
            commits=repository_commits(),
            ablation={"disabled_components": list(disabled_components)},
            slai_config=get_config_section("slai"),
        )
    return {
        "run_id": run_id,
        "report": str(report),
        "summary": summary,
        "stderr_tail": completed.stderr.strip()[-1500:],
    }


def _add_ablation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ablation",
        action="append",
        default=[],
        choices=sorted(_ARTIFACT_COMPONENTS),
        help="Record an actually disabled artifact component with the benchmark run.",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and benchmark SLAI-derived Harnyx SN67 artifacts.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")

    build = commands.add_parser("build")
    build.add_argument("profile", choices=["b0", "b1", "b2", "b3", "b4", "b5", "b6", "b7", "all"])
    build.add_argument("--official-validate", action="store_true")
    build.add_argument(
        "--disable",
        action="append",
        default=[],
        choices=sorted(_ARTIFACT_COMPONENTS),
    )

    smoke = commands.add_parser("slai-smoke")
    smoke.add_argument("--agent", action="append", default=[])
    smoke.add_argument("--reason")
    smoke.add_argument("--retrieve")

    evaluate = commands.add_parser("eval")
    evaluate.add_argument("--artifact", required=True)
    evaluate.add_argument("--strategy", required=True)
    evaluate.add_argument("--batch-id")
    evaluate.add_argument("--task-id")
    evaluate.add_argument(
        "--mode",
        choices=["vs-champion", "target-only"],
        default=None,
        help="Defaults to configs/harnyx.yaml harnyx.local_eval.default_mode.",
    )
    _add_ablation_arguments(evaluate)

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--artifact", required=True)
    benchmark.add_argument("--strategy", required=True)
    benchmark.add_argument("--suite", required=True)
    benchmark.add_argument("--source-batch-id", required=True)
    benchmark.add_argument("--sample-size", type=int)
    benchmark.add_argument("--parallelism", type=int)
    _add_ablation_arguments(benchmark)

    runs = commands.add_parser("runs")
    runs.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    result: Any = {}
    try:
        if args.command == "status":
            result = dependency_status()
        elif args.command == "build":
            if args.profile == "all":
                if args.disable:
                    parser.error("--disable is valid only for one profile")
                result = [
                    item.to_dict()
                    for item in build_all(official_validate=args.official_validate)
                ]
            else:
                result = build_artifact(
                    args.profile,
                    official_validate=args.official_validate,
                    disabled_components=tuple(args.disable),
                ).to_dict()
        elif args.command == "slai-smoke":
            from .adapters.slai import SlaiRuntime # type: ignore

            agents = list(args.agent)
            if args.reason and "reasoning" not in agents:
                agents.append("reasoning")
            if args.retrieve and "knowledge" not in agents:
                agents.append("knowledge")
            with SlaiRuntime(agents) as runtime:
                result = {"runtime": runtime.snapshot()}
                if args.reason:
                    result["reasoning"] = runtime.reason(args.reason)
                if args.retrieve:
                    result["retrieval"] = runtime.retrieve(args.retrieve)
                result["runtime"] = runtime.snapshot()
        elif args.command == "eval":
            result = local_eval(
                Path(args.artifact),
                strategy=args.strategy,
                batch_id=args.batch_id,
                task_id=args.task_id,
                mode=args.mode,
                disabled_components=tuple(args.ablation),
            )
        elif args.command == "benchmark":
            result = local_benchmark(
                Path(args.artifact),
                strategy=args.strategy,
                suite=args.suite,
                source_batch_id=args.source_batch_id,
                sample_size=args.sample_size,
                parallelism=args.parallelism,
                disabled_components=tuple(args.ablation),
            )
        else:
            with _store() as store:
                result = [
                    {
                        "run_id": run.run_id,
                        "run_kind": run.run_kind,
                        "strategy": run.strategy,
                        "artifact_hash": run.artifact_hash,
                        "score": run.score,
                        "cost_usd": run.cost_usd,
                        "median_runtime_ms": run.median_runtime_ms,
                        "p95_runtime_ms": run.p95_runtime_ms,
                        "error_rate": run.error_rate,
                        "created_at": run.created_at,
                    }
                    for run in store.latest_runs(limit=args.limit)
                ]
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except MinerError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
