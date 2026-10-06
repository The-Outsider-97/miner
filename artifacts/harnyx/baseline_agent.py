from __future__ import annotations

import json

from harnyx_miner_sdk.api import llm_chat
from harnyx_miner_sdk.context import ContextSnapshot
from harnyx_miner_sdk.decorators import entrypoint
from harnyx_miner_sdk.query import Query, Response
from harnyx_miner_sdk.structured_output import validate_output_against_schema

_PROVIDER = "chutes"
_MODEL = "deepseek-ai/DeepSeek-V3.2-TEE"


def _prompt(query: Query) -> str:
    if query.fast:
        instruction = "Answer every required component directly and correctly. Be concise. Add no unrelated claims or citations."
    else:
        instruction = "Answer accurately and self-contained. Do not invent citations or claim to have searched. State material uncertainty briefly."
    if query.output_schema is not None:
        instruction += " Return ONLY one JSON value matching this JSON Schema exactly; no Markdown fence: " + json.dumps(query.output_schema, ensure_ascii=False, sort_keys=True)
    return instruction + "\n\nQUESTION:\n" + query.text


def _parse_json(text: str):
    value = text.strip()
    if value.startswith("```"):
        newline = value.find("\n")
        if newline >= 0:
            value = value[newline + 1 :]
        if value.endswith("```"):
            value = value[:-3]
    return json.loads(value.strip())


def _fallback(schema):
    if "const" in schema:
        return schema["const"]
    values = schema.get("enum")
    if isinstance(values, list) and values:
        return values[0]
    kind = schema.get("type")
    if isinstance(kind, list):
        if "null" in kind:
            return None
        kind = kind[0] if kind else None
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        return {name: _fallback(properties.get(name) or {}) for name in (schema.get("required") or [])}
    if kind == "array":
        return [_fallback(schema.get("items") or {}) for _ in range(schema.get("minItems") or 0)]
    if kind == "integer":
        return int(schema.get("minimum") or 0)
    if kind == "number":
        return float(schema.get("minimum") or 0.0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "Unavailable"


@entrypoint("query")
async def query(query: Query, context: ContextSnapshot) -> Response:
    try:
        result = await llm_chat(
            provider=_PROVIDER,
            model=_MODEL,
            messages=[{"role": "user", "content": _prompt(query)}],
            temperature=0.0,
            max_output_tokens=512 if query.fast else 1800,
            timeout=min(25.0, context.time_budget.limit_seconds),
        )
        raw = (result.llm.raw_text or "").strip()
    except Exception:
        raw = ""
    if query.output_schema is None:
        return Response(text=raw or "No reliable answer was produced within the available tool budget.")
    try:
        output = _parse_json(raw)
        validate_output_against_schema(output, query.output_schema)
    except (json.JSONDecodeError, ValueError, TypeError):
        output = _fallback(query.output_schema)
    return Response(output=output)
