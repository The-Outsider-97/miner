"""Canonical Miner-side boundary for the pinned Harnyx query protocol."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from utils.miner_errors import CitationValidationError, HarnyxProtocolError, StructuredOutputError
from utils.miner_helpers import prepend_import_path, require_external_repository

_HARNYX_ROOT = require_external_repository("harnyx", "packages/miner-sdk/src/harnyx_miner_sdk/query.py")
prepend_import_path(_HARNYX_ROOT / "packages" / "miner-sdk" / "src")

from harnyx_miner_sdk.context import ContextSnapshot  # noqa: E402
from harnyx_miner_sdk.query import CitationRef, Query, Response  # noqa: E402
from harnyx_miner_sdk.structured_output import validate_output_against_schema  # noqa: E402

_CITATION_PATTERN = re.compile(r"\[\[(\d+)\]\]")
_MISSING = object()


@dataclass(frozen=True, slots=True)
class HarnyxRequest:
    text: str
    fast: bool
    structured: bool
    output_schema: Mapping[str, Any] | None
    time_limit_seconds: float
    budget_usd: float
    hard_limit_usd: float
    used_budget_usd: float
    remaining_budget_usd: float


def normalize_request(query: Query, context: ContextSnapshot) -> HarnyxRequest:
    budget = context.cost_budget
    return HarnyxRequest(
        text=query.text,
        fast=query.fast,
        structured=query.output_schema is not None,
        output_schema=query.output_schema,
        time_limit_seconds=context.time_budget.limit_seconds,
        budget_usd=budget.session_budget_usd,
        hard_limit_usd=budget.session_hard_limit_usd,
        used_budget_usd=budget.session_used_budget_usd,
        remaining_budget_usd=budget.session_remaining_budget_usd,
    )


def build_response(
    query: Query,
    *,
    text: str | None = None,
    output: Any = _MISSING,
    citations: Sequence[CitationRef] | None = None,
    note: str | None = None,
) -> Response:
    payload: dict[str, Any] = {}
    if query.output_schema is None:
        if output is not _MISSING:
            raise StructuredOutputError("plain-text Harnyx query cannot return Response.output")
        if text is None:
            raise HarnyxProtocolError("plain-text Harnyx query requires response text")
        payload["text"] = text
    else:
        if text is not None:
            raise StructuredOutputError("structured Harnyx query cannot return Response.text")
        if output is _MISSING:
            raise StructuredOutputError("structured Harnyx query requires Response.output")
        payload["output"] = output
    if citations is not None:
        payload["citations"] = list(citations)
    if note is not None:
        payload["note"] = note
    response = Response(**payload)
    validate_response(query, response)
    return response


def validate_response(query: Query, response: Response) -> None:
    selected = response.model_fields_set & {"text", "output"}
    if len(selected) != 1:
        raise HarnyxProtocolError("Harnyx response must contain exactly one answer field")
    if query.output_schema is None:
        if "text" not in selected:
            raise StructuredOutputError("query without output_schema requires Response.text")
    else:
        if "output" not in selected:
            raise StructuredOutputError("query with output_schema requires Response.output")
        try:
            validate_output_against_schema(response.output, query.output_schema)
        except ValueError as exc:
            raise StructuredOutputError(str(exc)) from exc
    citation_count = len(response.citations or ())
    for marker in _iter_citation_markers(response):
        if marker < 1 or marker > citation_count:
            raise CitationValidationError(
                "citation marker points outside Response.citations",
                context={"marker": marker, "citation_count": citation_count},
            )


def _iter_citation_markers(response: Response) -> list[int]:
    values: list[str] = []
    if response.text is not None:
        values.append(response.text)
    if response.note is not None:
        values.append(response.note)
    values.extend(_strings_in_json(response.output))
    markers: list[int] = []
    for value in values:
        markers.extend(int(match.group(1)) for match in _CITATION_PATTERN.finditer(value))
    return markers


def _strings_in_json(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        output: list[str] = []
        for item in value.values():
            output.extend(_strings_in_json(item))
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        output = []
        for item in value:
            output.extend(_strings_in_json(item))
        return output
    return []


def contract_snapshot() -> dict[str, Any]:
    return {
        "query_entrypoint": "async def query(query: Query, context: ContextSnapshot) -> Response",
        "fast_is_correctness_only": True,
        "structured_schema_draft": "2020-12",
        "max_response_citations": 200,
        "max_response_evidence_segments": 400,
        "max_text_chars": 80_000,
    }
