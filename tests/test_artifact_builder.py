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


def test_b6_uses_exact_anchor_retrieval_template(tmp_path: Path):
    result = build_artifact(
        "b6",
        output_path=tmp_path / "b6_agent.py",
        manifest_root=tmp_path / "manifests",
    )
    text = result.path.read_text(encoding="utf-8")

    assert "_temporal_anchors" in text
    assert "_candidate_matches_anchors" in text
    assert "_anchored_queries" in text
    assert "_focused_page_content" in text
    assert "_first_markdown_table" in text
    assert "fetch_page" in text
    assert "search_web" in text
    assert "'retrieval': True" in text
    assert "'verification': True" in text
    assert result.size_bytes <= _max_agent_bytes()

    compile(text, str(result.path), "exec")


def test_b7_requires_complete_anchor_coverage_and_table_diff(tmp_path: Path):
    result = build_artifact(
        "b7",
        output_path=tmp_path / "b7_agent.py",
        manifest_root=tmp_path / "manifests",
    )
    text = result.path.read_text(encoding="utf-8")

    assert "_search_exact_week" in text
    assert "_matches_exact_week" in text
    assert "_table_column_values" in text
    assert "_deterministic_table_comparison" in text
    assert "RETRIEVAL COVERAGE FAILURE" in text
    assert "DETERMINISTIC TABLE COMPARISON" in text
    assert "fetch_page" in text
    assert "search_web" in text
    assert "'retrieval': True" in text
    assert "'verification': True" in text
    assert result.size_bytes <= _max_agent_bytes()

    compile(text, str(result.path), "exec")


def test_b8_adds_focused_citations_and_public_verification_note(tmp_path: Path):
    result = build_artifact(
        "b8",
        output_path=tmp_path / "b8_agent.py",
        manifest_root=tmp_path / "manifests",
    )
    text = result.path.read_text(encoding="utf-8")

    assert "CitationSlice" in text
    assert "_focused_comparison_citations" in text
    assert "_comparison_extrema" in text
    assert "_context_slice" in text
    assert "_deterministic_output_from_evidence" in text
    assert "_comparison_note" in text
    assert "_MIN_CITATION_SLICE_CHARS = 100" in text
    assert "if deterministic_output is not None:" in text
    assert "note=_comparison_note(" in text
    assert "'retrieval': True" in text
    assert "'verification': True" in text
    assert result.size_bytes <= _max_agent_bytes()

    compile(text, str(result.path), "exec")


def test_b8_injects_distilled_runtime_deterministically(tmp_path: Path):
    first = build_artifact(
        "b8",
        output_path=tmp_path / "b8-one.py",
        manifest_root=tmp_path / "m1",
    )
    second = build_artifact(
        "b8",
        output_path=tmp_path / "b8-two.py",
        manifest_root=tmp_path / "m2",
    )

    one = first.path.read_text(encoding="utf-8")
    two = second.path.read_text(encoding="utf-8")

    assert first.sha256 == second.sha256
    assert one == two
    assert "__SLAI_RESEARCH_RUNTIME__" not in one
    assert "class SLAIResearchRuntime:" in one
    assert "class EvidenceLedger:" in one
    assert "class ResearchBudget:" in one
    assert "external.slai" not in one
    assert "src.agents" not in one
    assert one.count("async def query(") == 1
    assert first.size_bytes <= _max_agent_bytes()
    compile(one, str(first.path), "exec")
