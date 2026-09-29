import json

from slai_miner import _summary


def test_summary_parses_current_compact_harnyx_stdout():
    payload = {"batch_id": "b", "json_report": "/tmp/report.json"}
    assert _summary(json.dumps(payload)) == payload


def test_summary_tolerates_diagnostic_prefix_and_pretty_json():
    payload = {"run_id": "r", "json_report": "/tmp/report.json"}
    stdout = "diagnostic line\n" + json.dumps(payload, indent=2) + "\n"
    assert _summary(stdout) == payload
