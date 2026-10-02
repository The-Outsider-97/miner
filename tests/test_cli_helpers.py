import json
from pathlib import Path

import pytest

from miner.slai_miner import _parser, _report_path, _summary
from miner.utils.miner_errors import BenchmarkExecutionError


def test_summary_parses_current_compact_harnyx_stdout():
    payload = {"batch_id": "b", "json_report": "/tmp/report.json"}
    assert _summary(json.dumps(payload)) == payload


def test_summary_tolerates_diagnostic_prefix_and_pretty_json():
    payload = {"run_id": "r", "json_report": "/tmp/report.json"}
    stdout = "diagnostic line\n" + json.dumps(payload, indent=2) + "\n"
    assert _summary(stdout) == payload


def test_report_path_must_stay_inside_requested_output_directory(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    report = output / "report.json"
    report.write_text("{}", encoding="utf-8")
    assert _report_path(
        {"json_report": str(report)},
        key="json_report",
        output_dir=output,
    ) == report.resolve()

    escaped = tmp_path / "outside.json"
    escaped.write_text("{}", encoding="utf-8")
    with pytest.raises(BenchmarkExecutionError):
        _report_path(
            {"json_report": str(escaped)},
            key="json_report",
            output_dir=output,
        )


def test_cli_ablation_choices_match_real_artifact_components():
    parser = _parser()
    parsed = parser.parse_args(
        ["eval", "--artifact", "agent.py", "--strategy", "b3", "--ablation", "retrieval"]
    )
    assert parsed.ablation == ["retrieval"]

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["eval", "--artifact", "agent.py", "--strategy", "b3", "--ablation", "caching"]
        )
