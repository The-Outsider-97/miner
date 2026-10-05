from __future__ import annotations

from miner.capability_router import route_capabilities


def test_fast_task_stays_lightweight() -> None:
    plan = route_capabilities("What is a hash function?", fast=True)
    assert plan.depth == "lightweight"
    assert plan.capabilities == ("knowledge", "quality")
    assert plan.max_searches == 0


def test_current_research_task_requests_evidence_capabilities() -> None:
    plan = route_capabilities(
        "Research the latest evidence and compare two propulsion architectures."
    )
    assert plan.depth == "deep"
    assert plan.browse is True
    assert plan.verify is True
    assert "planning" in plan.capabilities
    assert "browser" in plan.capabilities
    assert "reader" in plan.capabilities
    assert "reasoning" in plan.capabilities
    assert "evaluation" in plan.capabilities
    assert plan.capabilities[-1] == "quality"


def test_long_evidentiary_task_can_be_exhaustive() -> None:
    text = " ".join(["research"] * 50) + " evidence study report"
    plan = route_capabilities(text)
    assert plan.depth == "exhaustive"
    assert plan.max_searches == 6
