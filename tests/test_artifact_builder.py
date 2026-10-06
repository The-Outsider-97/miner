import hashlib
from pathlib import Path

from miner.artifact_builder import _max_agent_bytes, build_artifact # type: ignore


def test_build_is_byte_deterministic(tmp_path: Path):
    first = build_artifact(
        "b3",
        output_path=tmp_path / "one.py",
        manifest_root=tmp_path / "m1",
    )
    second = build_artifact(
        "b3",
        output_path=tmp_path / "two.py",
        manifest_root=tmp_path / "m2",
    )
    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    assert hashlib.sha256(first.path.read_bytes()).hexdigest() == first.sha256
    assert first.size_bytes <= _max_agent_bytes()
    compile(first.path.read_text(encoding="utf-8"), str(first.path), "exec")


def test_ablation_changes_exported_strategy(tmp_path: Path):
    full = build_artifact(
        "b4",
        output_path=tmp_path / "full.py",
        manifest_root=tmp_path / "mf",
    )
    minus = build_artifact(
        "b4",
        output_path=tmp_path / "minus.py",
        manifest_root=tmp_path / "mm",
        disabled_components=("decomposition", "verification"),
    )
    assert full.sha256 != minus.sha256
    text = minus.path.read_text(encoding="utf-8")
    assert "'decomposition': False" in text
    assert "'verification': False" in text
    assert '@entrypoint("query")' in text
    assert "async def query(query: Query, context: ContextSnapshot) -> Response:" in text


def test_request_budget_state_is_not_written_into_global_profile(tmp_path: Path):
    result = build_artifact(
        "b4",
        output_path=tmp_path / "agent.py",
        manifest_root=tmp_path / "manifests",
    )
    text = result.path.read_text(encoding="utf-8")
    assert 'PROFILE["time_limit_seconds_hint"]' not in text
    assert 'PROFILE["minimum_budget_reserve_usd"]' not in text
    assert "time_limit_seconds = context.time_budget.limit_seconds" in text


def test_b5_uses_hardened_retrieval_template(tmp_path: Path):
    result = build_artifact(
        "b5",
        output_path=tmp_path / "b5_agent.py",
        manifest_root=tmp_path / "manifests",
    )
    text = result.path.read_text(encoding="utf-8")

    assert "from harnyx_miner_sdk.api import fetch_page" in text
    assert "search_web" in text
    assert "_search_with_failover" in text
    assert "_fetch_with_failover" in text
    assert '"exa"' in text
    assert '"tavily"' in text
    assert '"firecrawl"' in text
    assert '"desearch"' in text
    assert "'retrieval': True" in text
    assert "'verification': True" in text
    assert result.size_bytes <= _max_agent_bytes()

    compile(text, str(result.path), "exec")
