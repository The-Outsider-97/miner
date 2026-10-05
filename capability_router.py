"""General-purpose task capability routing for Miner-side SLAI orchestration.

The router is intentionally independent of Bittensor and Harnyx lifecycle state.
It classifies a research task into a small execution profile that downstream
integrations can consume without hard-coding subnet-specific behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityPlan:
    depth: str
    capabilities: tuple[str, ...]
    browse: bool
    verify: bool
    max_searches: int
    rationale: tuple[str, ...]


def route_capabilities(text: str, *, fast: bool = False) -> CapabilityPlan:
    normalized = " ".join(str(text).split()).strip().lower()
    words = normalized.split()
    length = len(words)

    comparative = any(
        token in normalized
        for token in (
            "compare",
            "versus",
            " vs ",
            "trade-off",
            "tradeoff",
            "pros and cons",
            "difference between",
        )
    )
    temporal = any(
        token in normalized
        for token in (
            "latest",
            "current",
            "today",
            "recent",
            "this week",
            "as of",
        )
    )
    evidentiary = any(
        token in normalized
        for token in (
            "source",
            "evidence",
            "citation",
            "research",
            "study",
            "paper",
            "report",
        )
    )
    uncertainty = any(
        token in normalized
        for token in (
            "uncertain",
            "controvers",
            "conflict",
            "ambiguous",
            "unknown",
            "risk",
        )
    )
    structured = any(
        token in normalized
        for token in (
            "analyze",
            "assessment",
            "evaluate",
            "recommend",
            "strategy",
            "architecture",
            "feasibility",
        )
    )

    if fast:
        depth = "lightweight"
    elif evidentiary and length >= 45:
        depth = "exhaustive"
    elif comparative or uncertainty or (structured and length >= 18):
        depth = "deep"
    elif evidentiary or temporal or structured or length >= 10:
        depth = "standard"
    else:
        depth = "lightweight"

    browse = temporal or evidentiary or depth in {"deep", "exhaustive"}
    verify = uncertainty or comparative or depth in {"deep", "exhaustive"}

    capabilities: list[str] = ["knowledge"]
    rationale: list[str] = []

    if depth != "lightweight":
        capabilities.insert(0, "planning")
        rationale.append("non-trivial task benefits from explicit planning")
    if browse:
        capabilities.extend(["browser", "reader"])
        rationale.append("task benefits from external evidence acquisition")
    if comparative or structured or depth in {"deep", "exhaustive"}:
        capabilities.append("reasoning")
        rationale.append("task requires synthesis across multiple considerations")
    if verify:
        capabilities.append("evaluation")
        rationale.append("task contains uncertainty/comparison that merits verification")
    capabilities.append("quality")

    seen: set[str] = set()
    ordered = tuple(cap for cap in capabilities if not (cap in seen or seen.add(cap)))
    max_searches = {
        "lightweight": 0 if not browse else 1,
        "standard": 2,
        "deep": 4,
        "exhaustive": 6,
    }[depth]

    return CapabilityPlan(
        depth=depth,
        capabilities=ordered,
        browse=browse,
        verify=verify,
        max_searches=max_searches,
        rationale=tuple(rationale),
    )
