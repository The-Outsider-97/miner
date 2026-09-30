"""Full-development-runtime bridge from Miner to the pinned SLAI v2.3 source.

Nothing in this module is exported into the Harnyx validator artifact. It uses
SLAI's process-scoped SharedMemory singleton and one AgentFactory, creates only
requested agents, and exposes timing so an agent's overhead can be measured
before its strategy is distilled into a standalone artifact.
"""

from __future__ import annotations

import time

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..utils.miner_errors import SLAIIntegrationError
from ..utils.miner_helpers import prepend_import_path, require_external_repository


@dataclass(frozen=True, slots=True)
class AgentMeasurement:
    agent: str
    operation: str
    elapsed_ms: float


class SlaiRuntime:
    """Own one AgentFactory lifecycle over SLAI's process-scoped SharedMemory."""

    def __init__(self, agents: Sequence[str] = ()) -> None:
        slai_root = require_external_repository("slai", "src/agents/agent_factory.py")
        prepend_import_path(slai_root)

        from logs.logger import get_logger # type: ignore
        from src.agents.agent_factory import AgentFactory # type: ignore
        from src.agents.collaborative.shared_memory import SharedMemory # type: ignore

        self._logger = get_logger("Miner SLAI Adapter")
        started = time.perf_counter()
        self.shared_memory = SharedMemory()
        self.factory = AgentFactory()
        self.initialization_ms = (time.perf_counter() - started) * 1000.0
        self._agents: dict[str, Any] = {}
        self.measurements: list[AgentMeasurement] = []
        self._closed = False
        for name in agents:
            self.get_agent(name)

    def _ensure_open(self) -> None:
        if self._closed:
            raise SLAIIntegrationError("SLAI runtime is already closed")

    def get_agent(self, name: str) -> Any:
        self._ensure_open()
        key = str(name).strip().lower()
        if not key:
            raise SLAIIntegrationError("SLAI agent name must not be blank")
        existing = self._agents.get(key)
        if existing is not None:
            return existing

        started = time.perf_counter()
        agent = self.factory.create(key, shared_memory=self.shared_memory)
        elapsed = (time.perf_counter() - started) * 1000.0
        self._agents[key] = agent
        self.measurements.append(AgentMeasurement(key, "initialize", elapsed))
        self._logger.info(
            "MINER | SLAI agent initialized | agent=%s | elapsed_ms=%.3f",
            key,
            elapsed,
        )
        return agent

    def reason(
        self,
        problem: Any,
        *,
        reasoning_type: str = "auto",
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        agent = self.get_agent("reasoning")
        operation = getattr(agent, "reason", None)
        if not callable(operation):
            raise SLAIIntegrationError("ReasoningAgent does not expose reason()")
        started = time.perf_counter()
        result = operation(problem, reasoning_type=reasoning_type, context=context)
        elapsed = (time.perf_counter() - started) * 1000.0
        self.measurements.append(AgentMeasurement("reasoning", "reason", elapsed))
        if not isinstance(result, dict):
            raise SLAIIntegrationError(
                "ReasoningAgent returned an unexpected result type",
                context={"actual_type": result.__class__.__name__},
            )
        return result

    def retrieve(self, query: str, *, k: int = 5) -> list[Any]:
        agent = self.get_agent("knowledge")
        operation = getattr(agent, "retrieve", None)
        if not callable(operation):
            raise SLAIIntegrationError("KnowledgeAgent does not expose retrieve()")
        started = time.perf_counter()
        result = operation(query, k=k)
        elapsed = (time.perf_counter() - started) * 1000.0
        self.measurements.append(AgentMeasurement("knowledge", "retrieve", elapsed))
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
            "measurements": [
                {
                    "agent": item.agent,
                    "operation": item.operation,
                    "elapsed_ms": item.elapsed_ms,
                }
                for item in self.measurements
            ],
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
