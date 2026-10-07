"""Development-time comparison bridge for the distilled research runtime.

This module is never injected into the Harnyx artifact. It exercises real SLAI
v2.3 operations exposed by the pinned source and compares their timing/results
with the lightweight deterministic runtime.
"""

from __future__ import annotations

import time

from dataclasses import asdict, dataclass
from typing import Any

from .slai import SlaiRuntime
from ..research.slai_research_runtime import SLAIResearchRuntime
from ..utils.miner_errors import SLAIIntegrationError


@dataclass(frozen=True, slots=True)
class ResearchComparison:
    task: str
    distilled_profile: dict[str, Any]
    distilled_plan: dict[str, Any]
    slai_capability_plan: dict[str, Any]
    agent_results: dict[str, Any]
    timings_ms: dict[str, float]


class SlaiResearchAdapter:
    """Optional development harness over actual SLAI AgentFactory operations."""

    def __init__(self, runtime: SlaiRuntime | None = None) -> None:
        self.runtime = runtime
        self._owns_runtime = runtime is None

    def compare(
        self,
        task: str,
        *,
        fast: bool = False,
        retrieve_k: int = 3,
        include_adaptive: bool = True,
        include_planning: bool = False,
        include_reasoning: bool = True,
        include_knowledge: bool = True,
        include_evaluation: bool = False,
        include_alignment: bool = False,
    ) -> ResearchComparison:
        distilled_started = time.perf_counter()
        distilled = SLAIResearchRuntime(
            task,
            fast=fast,
            structured_output=False,
        )
        profile = asdict(distilled.analyze())
        plan = asdict(distilled.planning_snapshot())
        distilled_ms = (
            time.perf_counter() - distilled_started
        ) * 1000.0

        runtime = self.runtime
        if runtime is None:
            runtime = SlaiRuntime()
            self.runtime = runtime

        capability_started = time.perf_counter()
        capability = runtime.plan_capabilities(
            task,
            fast=fast,
        )
        capability_ms = (
            time.perf_counter() - capability_started
        ) * 1000.0

        results: dict[str, Any] = {}
        timings = {
            "distilled": distilled_ms,
            "capability_plan": capability_ms,
        }

        if include_adaptive:
            results["adaptive"] = self._timed(
                timings,
                "adaptive.route_task",
                lambda: runtime.invoke(
                    "adaptive",
                    "route_task",
                    task,
                ),
            )

        if include_planning:
            results["planning"] = self._timed(
                timings,
                "planning.predict",
                lambda: runtime.invoke(
                    "planning",
                    "predict",
                    {
                        "goal": task,
                        "source": "miner_slai_research_adapter",
                    },
                ),
            )

        if include_knowledge:
            results["knowledge"] = self._timed(
                timings,
                "knowledge.retrieve",
                lambda: runtime.retrieve(
                    task,
                    k=retrieve_k,
                ),
            )

        if include_reasoning:
            results["reasoning"] = self._timed(
                timings,
                "reasoning.reason",
                lambda: runtime.reason(
                    task,
                    reasoning_type="auto",
                    context={
                        "source": "miner_slai_research_adapter",
                        "fast": fast,
                    },
                ),
            )

        if include_evaluation:
            results["evaluation"] = self._timed(
                timings,
                "evaluation.predict",
                lambda: runtime.invoke(
                    "evaluation",
                    "predict",
                    {
                        "task": task,
                        "distilled_profile": profile,
                        "distilled_plan": plan,
                    },
                ),
            )

        if include_alignment:
            results["alignment"] = self._timed(
                timings,
                "alignment.verify_alignment",
                lambda: runtime.invoke(
                    "alignment",
                    "verify_alignment",
                    {
                        "task": task,
                        "distilled_profile": profile,
                        "distilled_plan": plan,
                    },
                ),
            )

        return ResearchComparison(
            task=task,
            distilled_profile=profile,
            distilled_plan=plan,
            slai_capability_plan=asdict(capability),
            agent_results=results,
            timings_ms=timings,
        )

    @staticmethod
    def _timed(
        timings: dict[str, float],
        name: str,
        operation,
    ) -> Any:
        started = time.perf_counter()
        try:
            return operation()
        except SLAIIntegrationError as exc:
            return {
                "status": "unavailable",
                "error_type": exc.__class__.__name__,
                "context": dict(
                    getattr(exc, "context", None) or {}
                ),
            }
        finally:
            timings[name] = (
                time.perf_counter() - started
            ) * 1000.0

    def close(self) -> None:
        if self._owns_runtime and self.runtime is not None:
            self.runtime.close()
            self.runtime = None

    def __enter__(self) -> "SlaiResearchAdapter":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool:
        self.close()
        return False
