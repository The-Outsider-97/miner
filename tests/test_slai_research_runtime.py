from __future__ import annotations

import time

from research.slai_research_runtime import (
    ClaimState,
    EvidenceRecord,
    ProviderStatus,
    ResearchDepth,
    SLAIResearchRuntime,
)


def _runtime(
    text: str,
    *,
    fast: bool = False,
    structured: bool = False,
    output_fields=(),
) -> SLAIResearchRuntime:
    return SLAIResearchRuntime(
        text,
        fast=fast,
        structured_output=structured,
        output_fields=output_fields,
        started=time.monotonic(),
        time_limit_seconds=120.0,
        final_reserve_seconds=10.0,
        remaining_cost_usd=1.0,
        minimum_cost_reserve_usd=0.01,
    )


def _evidence(
    source_id: str,
    url: str,
    title: str,
    excerpt: str,
    *,
    relevance: float = 0.9,
    temporal_match: float = 1.0,
) -> EvidenceRecord:
    domain = url.split("/", 3)[2]
    return EvidenceRecord(
        source_id=source_id,
        url=url,
        domain=domain,
        title=title,
        retrieval_query="test query",
        provider="desearch",
        excerpt=excerpt,
        relevance=relevance,
        temporal_match=temporal_match,
        citation_eligible=True,
        source_text_length=len(excerpt),
    )


def test_fast_query_still_requires_research() -> None:
    runtime = _runtime(
        "What organization published the 2026 report and what value did it give?",
        fast=True,
    )

    assert runtime.profile.evidence_required is True
    assert runtime.depth in {
        ResearchDepth.LIGHT,
        ResearchDepth.STANDARD,
    }
    assert runtime.plan.initial_queries
    assert runtime.budget.max_rounds == 2
    assert runtime.budget.max_search_calls > 0
    assert runtime.budget.max_fetch_calls > 0


def test_task_profile_detects_temporal_comparison_and_determinism() -> None:
    runtime = _runtime(
        "Compare week 29 and week 30 of the 2026 table and calculate the largest decrease.",
        structured=True,
        output_fields=(
            "largest_decrease_agent",
            "largest_decrease_amount",
        ),
    )

    profile = runtime.analyze()

    assert profile.temporal is True
    assert profile.comparative is True
    assert profile.table is True
    assert profile.numerical is True
    assert profile.structured_output is True
    assert profile.deterministic_operation is True
    assert runtime.plan.deterministic_solver == "table_comparison"


def test_evidence_ledger_deduplicates_same_page() -> None:
    runtime = _runtime("What does the primary report say?")

    first, added_first = runtime.add_evidence(
        _evidence(
            "one",
            "https://example.gov/report",
            "Primary report",
            "The primary report states the requested factual answer.",
        )
    )
    second, added_second = runtime.add_evidence(
        _evidence(
            "two",
            "https://example.gov/report?tracking=1",
            "Primary report duplicate",
            "The primary report states the requested factual answer.",
        )
    )

    assert added_first is True
    assert added_second is False
    assert second is first
    assert len(runtime.ledger.records) == 1


def test_multi_source_claim_requires_independent_sources() -> None:
    runtime = _runtime(
        "Compare the two published sources and identify the difference."
    )

    runtime.add_evidence(
        _evidence(
            "one",
            "https://alpha.gov/a",
            "Alpha source",
            "Alpha source contains comparison evidence and the requested difference.",
        )
    )

    claims = {
        claim.claim_id: claim
        for claim in runtime.plan.claims
    }

    assert claims["source_coverage"].state == ClaimState.PARTIAL

    runtime.add_evidence(
        _evidence(
            "two",
            "https://beta.gov/b",
            "Beta source",
            "Beta source contains comparison evidence and the requested difference.",
        )
    )

    assert claims["source_coverage"].state == ClaimState.SUPPORTED


def test_gap_detection_generates_targeted_follow_up() -> None:
    runtime = _runtime(
        "Compare the 2026 versions from two sources and identify the change."
    )
    assert runtime.begin_round()

    runtime.add_evidence(
        _evidence(
            "one",
            "https://alpha.gov/2026",
            "2026 Alpha version",
            "2026 Alpha version contains one side of the comparison.",
        )
    )

    decision = runtime.should_continue_research()

    assert decision.continue_research is True
    assert decision.follow_up_queries
    joined = " ".join(decision.follow_up_queries).lower()
    assert (
        "independent primary source" in joined
        or "evidence" in joined
    )


def test_provider_credential_failure_is_terminal_for_task() -> None:
    runtime = _runtime("Find the requested fact.")

    health = runtime.mark_provider(
        "openrouter",
        error="tool provider credential unavailable",
    )

    assert health.status == ProviderStatus.CREDENTIAL_UNAVAILABLE
    assert runtime.provider_usable("openrouter") is False
    assert runtime.provider_usable("chutes") is True


def test_budget_stops_before_final_reserve() -> None:
    now = time.monotonic()
    runtime = SLAIResearchRuntime(
        "Find the requested fact.",
        fast=False,
        structured_output=False,
        started=now - 95.0,
        time_limit_seconds=100.0,
        final_reserve_seconds=10.0,
        remaining_cost_usd=1.0,
        minimum_cost_reserve_usd=0.01,
    )

    assert runtime.budget.final_reserve_intact(now) is False
    assert runtime.budget.can_search(now) is False
    assert runtime.budget.can_fetch(now) is False
    assert runtime.budget.can_llm(now) is False


def test_citation_budget_is_explicit_and_bounded() -> None:
    runtime = _runtime("Find the requested fact.")

    runtime.record_citation_chars(7200)
    runtime.record_citation_chars(7200)

    assert runtime.budget.materialized_citation_chars == 14400
    assert (
        runtime.budget.materialized_citation_chars
        < runtime.budget.max_materialized_citation_chars
    )
    assert runtime.budget.max_materialized_citation_chars == 80000


def test_confidence_retains_components() -> None:
    runtime = _runtime("What does the authoritative source report?")

    runtime.add_evidence(
        _evidence(
            "one",
            "https://example.gov/report",
            "Authoritative report",
            "The authoritative source reports the requested fact.",
        )
    )

    confidence = runtime.confidence(
        citation_support=1.0,
        schema_valid=True,
        deterministic_consistent=True,
    )

    assert 0.0 <= confidence.claim_coverage <= 1.0
    assert confidence.source_authority == 1.0
    assert confidence.citation_support == 1.0
    assert 0.0 <= confidence.aggregate <= 1.0


def test_verification_can_trigger_only_one_repair_cycle() -> None:
    runtime = _runtime(
        "Compare two sources and return the result."
    )

    first = runtime.verification_decision(
        "",
        schema_valid=True,
        citation_count=0,
    )

    assert first.continue_research is True
    assert first.reason.startswith("repair:")
    assert runtime.repair_used is True

    second = runtime.verification_decision(
        "",
        schema_valid=True,
        citation_count=0,
    )

    assert second.continue_research is False


def test_telemetry_contains_safe_research_state() -> None:
    runtime = _runtime("Find a 2026 source and summarize the fact.")
    runtime.mark_provider(
        "openrouter",
        error="credential unavailable",
    )
    runtime.confidence()

    telemetry = runtime.telemetry()

    assert telemetry["research_depth"] in {
        "light",
        "standard",
        "deep",
    }
    assert "task_profile" in telemetry
    assert "provider_failures" in telemetry
    assert "unresolved_claims" in telemetry
    assert "confidence" in telemetry
    assert "citation_materialized_character_estimate" in telemetry
    assert "api_key" not in str(telemetry).lower()
