"""Errors owned by the Miner/Harnyx integration boundary.

SLAI exceptions are deliberately not translated here: when an upstream SLAI
component fails, its native structured exception is allowed to propagate.  These
classes cover only Miner-owned configuration, artifact, protocol and benchmark
operations.
"""

from __future__ import annotations

from typing import Any, Mapping


class MinerError(RuntimeError):
    """Base class for failures whose ownership is the Miner repository."""

    code = "MIN-1000"

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = dict(context or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "context": dict(self.context)}


class MinerConfigurationError(MinerError):
    code = "MIN-1100"


class ExternalDependencyError(MinerError):
    code = "MIN-1101"


class HarnyxProtocolError(MinerError):
    code = "MIN-1200"


class CitationValidationError(HarnyxProtocolError):
    code = "MIN-1201"


class StructuredOutputError(HarnyxProtocolError):
    code = "MIN-1202"


class ArtifactBuildError(MinerError):
    code = "MIN-1300"


class ArtifactValidationError(ArtifactBuildError):
    code = "MIN-1301"


class BudgetExceededError(MinerError):
    code = "MIN-1400"


class DeadlineExceededError(MinerError):
    code = "MIN-1401"


class ProviderExecutionError(MinerError):
    code = "MIN-1500"


class BenchmarkExecutionError(MinerError):
    code = "MIN-1600"


class SLAIIntegrationError(MinerError):
    code = "MIN-1700"
