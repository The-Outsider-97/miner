from __future__ import annotations

import json
import re
import time

from harnyx_miner_sdk.api import llm_chat, search_web, tooling_info
from harnyx_miner_sdk.context import ContextSnapshot
from harnyx_miner_sdk.decorators import entrypoint
from harnyx_miner_sdk.query import CitationRef, Query, Response
from harnyx_miner_sdk.structured_output import validate_output_against_schema

PROFILE = {'analysis_max_output_tokens': 700,
 'decomposition': False,
 'evidence_limit': 5,
 'evidence_ranking': False,
 'fast_max_output_tokens': 512,
 'id': 'b1',
 'minimum_final_seconds': 12.0,
 'normal_max_output_tokens': 1800,
 'provider_routing': True,
 'reserve_budget_fraction': 0.25,
 'retrieval': False,
 'routes': [{'model': 'deepseek-ai/DeepSeek-V3.2-TEE', 'provider': 'chutes'},
            {'model': 'openai/gpt-oss-120b', 'provider': 'openrouter'},
            {'model': 'openai/gpt-oss-120b', 'provider': 'ai_gateway'}],
 'search_provider': 'desearch',
 'search_results': 5,
 'tool_timeout_seconds': 25.0,
 'verification': False,
 'verification_max_output_tokens': 900}
_MARKER = re.compile(r"\[\[(\d+)\]\]")
_WORD = re.compile(r"[a-z0-9]{3,}")


def _task_policy(query: Query):
    text = " ".join(query.text.lower().split())
    words = _WORD.findall(text)
    comparative = any(token in text for token in ("compare", "versus", " vs ", "difference between", "trade-off", "tradeoff"))
    temporal = any(token in text for token in ("latest", "current", "today", "recent", "as of", "this week"))
    evidence = any(token in text for token in ("source", "evidence", "citation", "research", "study", "paper", "report"))
    analytical = any(token in text for token in ("analyze", "assess", "evaluate", "recommend", "feasibility", "architecture", "strategy"))
    uncertain = any(token in text for token in ("uncertain", "controvers", "conflict", "ambiguous", "risk"))

    if query.fast:
        depth = "lightweight"
    elif comparative or uncertain or (analytical and len(words) >= 18):
        depth = "deep"
    elif temporal or evidence or analytical or len(words) >= 10:
        depth = "standard"
    else:
        depth = "lightweight"

    return {
        "depth": depth,
        "needs_plan": depth in ("standard", "deep") and PROFILE["decomposition"],
        "needs_retrieval": PROFILE["retrieval"] and (temporal or evidence or comparative or depth == "deep"),
        "needs_verification": PROFILE["verification"] and (comparative or uncertain or depth == "deep"),
        "search_results": max(2, PROFILE["search_results"] // 2) if depth == "standard" else PROFILE["search_results"],
        "evidence_limit": max(2, PROFILE["evidence_limit"] // 2) if depth == "standard" else PROFILE["evidence_limit"],
    }


def _answer_prompt(query: Query, evidence: str, plan: str) -> str:
    if query.fast:
        instruction = "Answer every required component directly and correctly. Be concise. Add no citations or unrelated claims."
    elif evidence:
        instruction = "Answer as a research assistant. Ground factual claims in the supplied evidence and use only the exact [[n]] markers shown. Distinguish supported findings from material uncertainty."
    else:
        instruction = "Answer accurately and self-contained. Do not invent citations. State material uncertainty briefly."
    if query.output_schema is not None:
        instruction += " Return ONLY one JSON value matching this JSON Schema exactly; no Markdown fence: " + json.dumps(query.output_schema, ensure_ascii=False, sort_keys=True)
    parts = [instruction, "QUESTION:\n" + query.text]
    if plan:
        parts.append("PLANNING NOTES:\n" + plan)
    if evidence:
        parts.append("EVIDENCE:\n" + evidence)
    return "\n\n".join(parts)


def _parse_json(text: str):
    value = text.strip()
    if value.startswith("```"):
        newline = value.find("\n")
        if newline >= 0:
            value = value[newline + 1 :]
        if value.endswith("```"):
            value = value[:-3]
    return json.loads(value.strip())


def _schema_fallback(schema):
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for keyword in ("oneOf", "anyOf"):
        variants = schema.get(keyword)
        if isinstance(variants, list) and variants:
            return _schema_fallback(variants[0])
    kind = schema.get("type")
    if isinstance(kind, list):
        if "null" in kind:
            return None
        kind = kind[0] if kind else None
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        return {key: _schema_fallback(properties.get(key) or {}) for key in (schema.get("required") or [])}
    if kind == "array":
        return [_schema_fallback(schema.get("items") or {}) for _ in range(schema.get("minItems") or 0)]
    if kind == "integer":
        return int(schema.get("minimum") or 0)
    if kind == "number":
        return float(schema.get("minimum") or 0.0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "Unavailable"


def _sanitize_markers(text: str, count: int) -> str:
    def replace(match):
        index = int(match.group(1))
        return match.group(0) if 1 <= index <= count else ""
    return _MARKER.sub(replace, text).strip()


def _domain(url: str) -> str:
    value = (url or "").lower().strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    return value.split("/", 1)[0].removeprefix("www.")


def _source_score(item, query_words):
    title = (item.title or "").lower()
    note = (item.note or "").lower()
    url = (item.url or "").lower()
    haystack = title + " " + note
    overlap = sum(1 for word in query_words if word in haystack)
    domain = _domain(url)
    authority = 0
    if domain.endswith(".gov") or domain.endswith(".edu"):
        authority = 4
    elif any(token in domain for token in ("nature.com", "science.org", "who.int", "oecd.org", "worldbank.org", "reuters.com")):
        authority = 3
    elif domain:
        authority = 1
    substance = min(len(note), 1800) // 300
    return authority * 100 + overlap * 10 + substance


def _select_evidence(results, query_text: str, limit: int):
    query_words = set(_WORD.findall(query_text.lower()))
    seen_urls = set()
    seen_notes = set()
    unique = []
    for item in results:
        note = " ".join((item.note or "").split()).strip()
        if not note:
            continue
        url = (item.url or "").strip().lower()
        note_key = note[:240].lower()
        if (url and url in seen_urls) or note_key in seen_notes:
            continue
        if url:
            seen_urls.add(url)
        seen_notes.add(note_key)
        unique.append(item)
    if PROFILE["evidence_ranking"]:
        unique.sort(key=lambda item: _source_score(item, query_words), reverse=True)
    return unique[:limit]


async def _route():
    default = PROFILE["routes"][0]
    if not PROFILE["provider_routing"]:
        return default
    try:
        info = await tooling_info(timeout=5.0)
    except Exception:
        return default
    allowed = info.response.get("allowed_llm_provider_models") or {}
    for route in PROFILE["routes"]:
        if route["model"] in (allowed.get(route["provider"]) or []):
            return route
    return default


async def _chat(route, prompt: str, tokens: int, timeout: float):
    routes = [route]
    default = PROFILE["routes"][0]
    if route != default:
        routes.append(default)
    for candidate in routes[:2]:
        try:
            result = await llm_chat(
                provider=candidate["provider"], model=candidate["model"],
                messages=[{"role": "user", "content": prompt}], temperature=0.0,
                max_output_tokens=tokens, timeout=max(1.0, min(PROFILE["tool_timeout_seconds"], timeout)),
            )
            return (result.llm.raw_text or "").strip(), result.budget.session_remaining_budget_usd
        except Exception:
            continue
    return "", None


def _remaining_seconds(started: float, time_limit_seconds: float, reserve: float = 1.0) -> float:
    return max(1.0, time_limit_seconds - (time.monotonic() - started) - reserve)


async def _plan(query: Query, route, policy, remaining: float, started: float, time_limit_seconds: float):
    if not policy["needs_plan"]:
        return "", remaining
    prompt = "Decompose this research question into at most four factual checks and identify what evidence would resolve each check. Return planning notes only, not the answer.\n\n" + query.text
    planned, updated = await _chat(route, prompt, PROFILE["analysis_max_output_tokens"], _remaining_seconds(started, time_limit_seconds, PROFILE["minimum_final_seconds"]))
    return planned, remaining if updated is None else updated


async def _evidence(query: Query, plan: str, policy, remaining: float, started: float, time_limit_seconds: float):
    if not policy["needs_retrieval"]:
        return "", [], remaining
    search_text = query.text if not plan else query.text + "\nResearch checks:\n" + plan
    try:
        search = await search_web(
            search_text,
            provider=PROFILE["search_provider"],
            num=policy["search_results"],
            timeout=max(1.0, min(PROFILE["tool_timeout_seconds"], _remaining_seconds(started, time_limit_seconds, PROFILE["minimum_final_seconds"]))),
        )
    except Exception:
        return "", [], remaining
    selected = _select_evidence(search.results, query.text, policy["evidence_limit"])
    lines = []
    citations = []
    for index, item in enumerate(selected, start=1):
        title = (item.title or item.url or "source").strip()
        note = " ".join((item.note or "").split()).strip()[:1800]
        lines.append("SOURCE " + str(index) + " [[" + str(index) + "]] " + title + "\n" + note)
        citations.append(CitationRef(receipt_id=search.receipt_id, result_id=item.result_id))
    return "\n\n".join(lines), citations, search.budget.session_remaining_budget_usd


async def _structured(query: Query, route, raw: str, remaining: float, started: float, time_limit_seconds: float):
    schema = query.output_schema or {}
    try:
        output = _parse_json(raw)
        validate_output_against_schema(output, schema)
        return output, remaining
    except (json.JSONDecodeError, ValueError, TypeError):
        if _remaining_seconds(started, time_limit_seconds, PROFILE["minimum_final_seconds"]) <= 1.0:
            return _schema_fallback(schema), remaining
        repair = "Repair this candidate into exactly one JSON value matching the schema. Return JSON only.\nSCHEMA:\n" + json.dumps(schema, ensure_ascii=False, sort_keys=True) + "\nCANDIDATE:\n" + raw
        fixed, updated = await _chat(route, repair, PROFILE["normal_max_output_tokens"], _remaining_seconds(started, time_limit_seconds, PROFILE["minimum_final_seconds"]))
        remaining = remaining if updated is None else updated
        try:
            output = _parse_json(fixed)
            validate_output_against_schema(output, schema)
            return output, remaining
        except (json.JSONDecodeError, ValueError, TypeError):
            return _schema_fallback(schema), remaining


async def _verify(query: Query, route, answer, evidence: str, policy, remaining: float, started: float, time_limit_seconds: float, minimum_budget_reserve_usd: float):
    if not policy["needs_verification"]:
        return answer, remaining
    elapsed = time.monotonic() - started
    if remaining <= minimum_budget_reserve_usd or time_limit_seconds - elapsed <= PROFILE["minimum_final_seconds"]:
        return answer, remaining
    if query.output_schema is not None:
        prompt = "Check and correct only material errors in the candidate against the question, evidence, and schema. Return JSON only.\nQUESTION:\n" + query.text + "\nEVIDENCE:\n" + evidence + "\nSCHEMA:\n" + json.dumps(query.output_schema, ensure_ascii=False, sort_keys=True) + "\nCANDIDATE:\n" + json.dumps(answer, ensure_ascii=False, sort_keys=True)
    else:
        prompt = "Correct only material factual, support, or coverage errors using the evidence. Remove unsupported assertions. Preserve valid [[n]] markers. Return only the corrected answer.\nQUESTION:\n" + query.text + "\nEVIDENCE:\n" + evidence + "\nCANDIDATE:\n" + str(answer)
    checked, updated = await _chat(route, prompt, PROFILE["verification_max_output_tokens"], _remaining_seconds(started, time_limit_seconds, 1.0))
    remaining = remaining if updated is None else updated
    if not checked:
        return answer, remaining
    if query.output_schema is None:
        return checked, remaining
    try:
        output = _parse_json(checked)
        validate_output_against_schema(output, query.output_schema)
        return output, remaining
    except (json.JSONDecodeError, ValueError, TypeError):
        return answer, remaining


@entrypoint("query")
async def query(query: Query, context: ContextSnapshot) -> Response:
    started = time.monotonic()
    remaining = context.cost_budget.session_remaining_budget_usd
    time_limit_seconds = context.time_budget.limit_seconds
    minimum_budget_reserve_usd = max(0.005, context.cost_budget.session_budget_usd * PROFILE["reserve_budget_fraction"])
    policy = _task_policy(query)
    route = await _route()

    plan, remaining = await _plan(query, route, policy, remaining, started, time_limit_seconds)
    evidence, citations, remaining = await _evidence(query, plan, policy, remaining, started, time_limit_seconds)
    raw, updated = await _chat(
        route,
        _answer_prompt(query, evidence, plan),
        PROFILE["fast_max_output_tokens"] if query.fast else PROFILE["normal_max_output_tokens"],
        _remaining_seconds(started, time_limit_seconds, 1.0),
    )
    if updated is not None:
        remaining = updated

    if query.output_schema is not None:
        output, remaining = await _structured(query, route, raw, remaining, started, time_limit_seconds)
        output, remaining = await _verify(query, route, output, evidence, policy, remaining, started, time_limit_seconds, minimum_budget_reserve_usd)
        return Response(output=output, citations=citations or None)

    if not raw:
        raw = "No reliable answer was produced within the available tool budget."
    answer = _sanitize_markers(raw, len(citations))
    answer, remaining = await _verify(query, route, answer, evidence, policy, remaining, started, time_limit_seconds, minimum_budget_reserve_usd)
    answer = _sanitize_markers(str(answer), len(citations))
    if citations and "[[" not in answer:
        answer += "\n\nSources: " + "".join("[[" + str(i) + "]]" for i in range(1, len(citations) + 1))
    return Response(text=answer, citations=citations or None)
