"""Full-development-runtime bridge from Miner to the pinned SLAI v2.3 source.

Nothing in this module is exported into the Harnyx validator artifact. It uses
SLAI's process-scoped SharedMemory singleton and one AgentFactory, creates only
requested agents, and exposes timing so an agent's overhead can be measured
before its strategy is distilled into a standalone artifact.
"""

from __future__ import annotations

import time

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from ..capability_router import CapabilityPlan, route_capabilities
from ..utils.miner_errors import SLAIIntegrationError
from ..utils.miner_helpers import prepend_import_path, require_external_repository


@dataclass(frozen=True, slots=True)
class AgentMeasurement:
    agent: str
    operation: str
    elapsed_ms: float
    success: bool = True
    input_size: int | None = None
    output_size: int | None = None
    error_type: str | None = None


class SlaiRuntime:
    """Own one AgentFactory lifecycle over SLAI's process-scoped SharedMemory."""

    def __init__(self, agents: Sequence[str] = ()) -> None:
        slai_root = require_external_repository("slai", "src/agents/agent_factory.py")
        prepend_import_path(slai_root)

        from logs.logger import get_logger  # type: ignore
        from src.agents.agent_factory import AgentFactory  # type: ignore
        from src.agents.collaborative.shared_memory import SharedMemory  # type: ignore

        self._logger = get_logger("Miner SLAI Adapter")
        started = time.perf_counter()
        self.shared_memory = SharedMemory()
        self.factory = AgentFactory()
        self.initialization_ms = (time.perf_counter() - started) * 1000.0
        self._agents: dict[str, Any] = {}
        self.measurements: list[AgentMeasurement] = []
        self._plans: list[CapabilityPlan] = []
        self._closed = False
        for name in agents:
            self.get_agent(name)

    def _ensure_open(self) -> None:
        if self._closed:
            raise SLAIIntegrationError("SLAI runtime is already closed")

    def plan_capabilities(self, task: str, *, fast: bool = False) -> CapabilityPlan:
        """Return a general-purpose capability plan without instantiating agents."""
        self._ensure_open()
        plan = route_capabilities(task, fast=fast)
        self._plans.append(plan)
        return plan

    def get_agent(self, name: str) -> Any:
        self._ensure_open()
        key = str(name).strip().lower()
        if not key:
            raise SLAIIntegrationError("SLAI agent name must not be blank")
        existing = self._agents.get(key)
        if existing is not None:
            return existing

        started = time.perf_counter()
        try:
            agent = self.factory.create(key, shared_memory=self.shared_memory)
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            self.measurements.append(
                AgentMeasurement(
                    key,
                    "initialize",
                    elapsed,
                    success=False,
                    error_type=exc.__class__.__name__,
                )
            )
            raise SLAIIntegrationError(
                "SLAI agent initialization failed",
                context={"agent": key, "error_type": exc.__class__.__name__},
            ) from exc

        elapsed = (time.perf_counter() - started) * 1000.0
        self._agents[key] = agent
        self.measurements.append(AgentMeasurement(key, "initialize", elapsed))
        self._logger.info(
            "MINER | SLAI agent initialized | agent=%s | elapsed_ms=%.3f",
            key,
            elapsed,
        )
        return agent

    def invoke(
        self,
        agent_name: str,
        operation_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke one known SLAI operation and persist success/failure telemetry."""
        agent = self.get_agent(agent_name)
        operation = getattr(agent, operation_name, None)
        if not callable(operation):
            raise SLAIIntegrationError(
                "SLAI agent does not expose the requested operation",
                context={"agent": agent_name, "operation": operation_name},
            )

        input_size = _estimate_size((args, kwargs))
        started = time.perf_counter()
        try:
            result = operation(*args, **kwargs)
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            self.measurements.append(
                AgentMeasurement(
                    str(agent_name).lower(),
                    operation_name,
                    elapsed,
                    success=False,
                    input_size=input_size,
                    error_type=exc.__class__.__name__,
                )
            )
            raise SLAIIntegrationError(
                "SLAI agent invocation failed",
                context={
                    "agent": str(agent_name).lower(),
                    "operation": operation_name,
                    "error_type": exc.__class__.__name__,
                },
            ) from exc

        elapsed = (time.perf_counter() - started) * 1000.0
        self.measurements.append(
            AgentMeasurement(
                str(agent_name).lower(),
                operation_name,
                elapsed,
                input_size=input_size,
                output_size=_estimate_size(result),
            )
        )
        return result

    def reason(
        self,
        problem: Any,
        *,
        reasoning_type: str = "auto",
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.invoke(
            "reasoning",
            "reason",
            problem,
            reasoning_type=reasoning_type,
            context=context,
        )
        if not isinstance(result, dict):
            raise SLAIIntegrationError(
                "ReasoningAgent returned an unexpected result type",
                context={"actual_type": result.__class__.__name__},
            )
        return result

    def retrieve(self, query: str, *, k: int = 5) -> list[Any]:
        result = self.invoke("knowledge", "retrieve", query, k=k)
        if not isinstance(result, list):
            raise SLAIIntegrationError(
                "KnowledgeAgent returned an unexpected retrieval result type",
                context={"actual_type": result.__class__.__name__},
            )
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "initialization_ms": self.initialization_ms,
            "agents": sorted(self._agents),
            "plans": [asdict(plan) for plan in self._plans],
            "measurements": [asdict(item) for item in self.measurements],
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.factory.shutdown()
        finally:
            # SharedMemory is a process singleton in SLAI. Closing it would poison
            # subsequent Miner experiments in the same process because SLAI does
            # not reinitialize a closed singleton. Clear experiment values instead;
            # the process-scoped cleaner is released when the process exits.
            self.shared_memory.clear_all()

    def __enter__(self) -> "SlaiRuntime":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False


def _estimate_size(value: Any) -> int | None:
    """Return a cheap deterministic size proxy without serializing arbitrary objects."""
    if value is None:
        return 0
    if isinstance(value, (str, bytes, bytearray)):
        return len(value)
    if isinstance(value, Mapping):
        return sum(len(str(key)) + (_estimate_size(item) or 0) for key, item in value.items())
    if isinstance(value, Sequence):
        return sum(_estimate_size(item) or 0 for item in value)
    try:
        return len(str(value))
    except Exception:
        return None
