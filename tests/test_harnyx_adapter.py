import pytest

from adapters.harnyx import CitationRef, ContextSnapshot, Query, build_response, normalize_request
from harnyx_miner_sdk.tools.http_models import ToolBudgetDTO
from harnyx_miner_sdk.tools.time_budget import ExecutionTimeBudgetDTO
from utils.miner_errors import CitationValidationError, StructuredOutputError


def _context():
    return ContextSnapshot(cost_budget=ToolBudgetDTO(session_budget_usd=0.1,session_hard_limit_usd=0.12,session_used_budget_usd=0.02,session_remaining_budget_usd=0.08),time_budget=ExecutionTimeBudgetDTO(limit_seconds=300.0))


def test_fast_and_budget_normalization():
    request=normalize_request(Query(text="question",fast=True),_context())
    assert request.fast is True
    assert request.time_limit_seconds==300.0
    assert request.remaining_budget_usd==0.08


def test_plain_query_rejects_output():
    with pytest.raises(StructuredOutputError): build_response(Query(text="q"),output={"x":1})


def test_structured_output_uses_query_schema():
    query=Query(text="q",output_schema={"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"value":{"type":"integer"}},"required":["value"],"additionalProperties":False})
    assert build_response(query,output={"value":3}).output=={"value":3}
    with pytest.raises(StructuredOutputError): build_response(query,output={"value":"wrong"})


def test_citation_pointer_must_address_receipt_ref():
    citation=CitationRef(receipt_id="receipt-1",result_id="result-1")
    assert build_response(Query(text="q"),text="Supported [[1]].",citations=[citation]).text
    with pytest.raises(CitationValidationError): build_response(Query(text="q"),text="Broken [[2]].",citations=[citation])
