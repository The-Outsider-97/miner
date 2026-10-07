"""General-purpose distilled SLAI research orchestration runtime.

This module deliberately contains no Bittensor or Harnyx imports. It distills
SLAI v2.3 ideas that are useful for bounded research: adaptive depth,
deterministic planning, evidence/provenance tracking, gap detection, provider
health, budget-aware stopping, confidence, and verification.

The code between ARTIFACT_RUNTIME_BEGIN/END is injected verbatim into the
standalone B8 Harnyx artifact at build time.
"""

from __future__ import annotations

import hashlib
import re
import time

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


# ARTIFACT_RUNTIME_BEGIN
class ResearchDepth(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchStage(str, Enum):
    ANALYZE = "analyze"
    PLAN = "plan"
    RETRIEVE = "retrieve"
    ASSESS_EVIDENCE = "assess_evidence"
    IDENTIFY_GAPS = "identify_gaps"
    FOLLOW_UP_RETRIEVAL = "follow_up_retrieval"
    SOLVE = "solve"
    VERIFY = "verify"
    REPAIR = "repair"
    FINALIZE = "finalize"


class ClaimState(str, Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"


class ProviderStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    TIMEOUT_PRONE = "timeout_prone"
    RATE_LIMITED = "rate_limited"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    HARD_FAILURE = "hard_failure"


@dataclass(slots=True)
class TaskProfile:
    factual: bool = True
    temporal: bool = False
    comparative: bool = False
    table: bool = False
    multi_source: bool = False
    document_extraction: bool = False
    enumeration: bool = False
    numerical: bool = False
    structured_output: bool = False
    evidence_required: bool = True
    high_uncertainty: bool = False
    conflict_risk: bool = False
    deterministic_operation: bool = False


@dataclass(slots=True)
class ClaimRequirement:
    claim_id: str
    description: str
    required_sources: int = 1
    state: ClaimState = ClaimState.MISSING
    source_ids: set[str] = field(default_factory=set)
    conflicting_source_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class EvidenceRecord:
    source_id: str
    url: str
    domain: str
    title: str
    retrieval_query: str
    provider: str
    excerpt: str
    authority: float = 0.0
    relevance: float = 0.0
    temporal_match: float = 1.0
    citation_eligible: bool = True
    source_text_length: int = 0
    fingerprint: str = ""
    supported_claims: set[str] = field(default_factory=set)
    provenance: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.fingerprint:
            normalized = " ".join(
                (self.url + "\n" + self.title + "\n" + self.excerpt[:1600])
                .lower()
                .split()
            )
            self.fingerprint = hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest()[:20]


@dataclass(slots=True)
class ResearchPlan:
    claims: list[ClaimRequirement]
    initial_queries: list[str]
    stop_conditions: tuple[str, ...]
    preferred_source_count: int
    deterministic_solver: str | None = None


@dataclass(slots=True)
class ResearchBudget:
    started: float
    time_limit_seconds: float
    final_reserve_seconds: float
    max_rounds: int
    max_search_calls: int
    max_fetch_calls: int
    max_llm_calls: int
    max_materialized_citation_chars: int
    minimum_cost_reserve_usd: float = 0.0
    remaining_cost_usd: float | None = None
    rounds: int = 0
    search_calls: int = 0
    fetch_calls: int = 0
    llm_calls: int = 0
    materialized_citation_chars: int = 0

    def remaining_seconds(self, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        return max(
            0.0,
            self.time_limit_seconds - (current - self.started),
        )

    def final_reserve_intact(self, now: float | None = None) -> bool:
        return self.remaining_seconds(now) > self.final_reserve_seconds

    def cost_reserve_intact(self) -> bool:
        if self.remaining_cost_usd is None:
            return True
        return self.remaining_cost_usd > self.minimum_cost_reserve_usd

    def can_search(self, now: float | None = None) -> bool:
        return (
            self.final_reserve_intact(now)
            and self.cost_reserve_intact()
            and self.search_calls < self.max_search_calls
        )

    def can_fetch(self, now: float | None = None) -> bool:
        return (
            self.final_reserve_intact(now)
            and self.cost_reserve_intact()
            and self.fetch_calls < self.max_fetch_calls
        )

    def can_llm(self, now: float | None = None) -> bool:
        return (
            self.final_reserve_intact(now)
            and self.cost_reserve_intact()
            and self.llm_calls < self.max_llm_calls
        )

    def can_round(self, now: float | None = None) -> bool:
        return (
            self.rounds < self.max_rounds
            and self.can_search(now)
        )


@dataclass(slots=True)
class ProviderHealth:
    status: ProviderStatus = ProviderStatus.UNKNOWN
    failures: int = 0
    successes: int = 0
    last_error: str | None = None

    @property
    def usable(self) -> bool:
        return self.status not in {
            ProviderStatus.CREDENTIAL_UNAVAILABLE,
            ProviderStatus.HARD_FAILURE,
        }


@dataclass(slots=True)
class ConfidenceComponents:
    claim_coverage: float = 0.0
    source_authority: float = 0.0
    temporal_match: float = 1.0
    source_agreement: float = 1.0
    deterministic_consistency: float = 1.0
    citation_support: float = 0.0
    schema_validity: float = 1.0

    @property
    def aggregate(self) -> float:
        weighted = (
            self.claim_coverage * 0.30
            + self.source_authority * 0.13
            + self.temporal_match * 0.15
            + self.source_agreement * 0.12
            + self.deterministic_consistency * 0.12
            + self.citation_support * 0.10
            + self.schema_validity * 0.08
        )
        return max(0.0, min(1.0, weighted))


@dataclass(slots=True)
class ResearchDecision:
    continue_research: bool
    reason: str
    follow_up_queries: list[str] = field(default_factory=list)


class EvidenceLedger:
    """Deterministic evidence/provenance store with conservative deduplication."""

    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []
        self._by_url: dict[str, EvidenceRecord] = {}
        self._by_fingerprint: dict[str, EvidenceRecord] = {}

    @staticmethod
    def _canonical_url(url: str) -> str:
        value = (url or "").strip().lower()
        if value.endswith("/"):
            value = value[:-1]
        value = re.sub(r"[?#].*$", "", value)
        return value

    def add(self, record: EvidenceRecord) -> tuple[EvidenceRecord, bool]:
        url_key = self._canonical_url(record.url)

        duplicate = (
            self._by_url.get(url_key)
            if url_key
            else None
        )
        if duplicate is None:
            duplicate = self._by_fingerprint.get(record.fingerprint)

        if duplicate is not None:
            duplicate.supported_claims.update(record.supported_claims)
            duplicate.provenance.extend(
                item
                for item in record.provenance
                if item not in duplicate.provenance
            )
            duplicate.authority = max(
                duplicate.authority,
                record.authority,
            )
            duplicate.relevance = max(
                duplicate.relevance,
                record.relevance,
            )
            duplicate.temporal_match = max(
                duplicate.temporal_match,
                record.temporal_match,
            )
            return duplicate, False

        self.records.append(record)

        if url_key:
            self._by_url[url_key] = record
        self._by_fingerprint[record.fingerprint] = record

        return record, True

    def domains(self) -> set[str]:
        return {
            record.domain
            for record in self.records
            if record.domain
        }

    def source_ids_for_claim(self, claim_id: str) -> set[str]:
        return {
            record.source_id
            for record in self.records
            if claim_id in record.supported_claims
        }

    def evidence_for_claim(self, claim_id: str) -> list[EvidenceRecord]:
        return [
            record
            for record in self.records
            if claim_id in record.supported_claims
        ]


class SLAIResearchRuntime:
    """Compact bounded research controller derived from SLAI v2.3 patterns."""

    _TEMPORAL = re.compile(
        r"\b(?:20\d{2}|week\s+\d{1,2}|"
        r"january|february|march|april|may|june|july|august|"
        r"september|october|november|december|version|edition|release)\b",
        re.IGNORECASE,
    )
    _COMPARATIVE = re.compile(
        r"\b(?:compare|comparison|versus|vs\.?|difference|increase|decrease|"
        r"higher|lower|largest|smallest|maximum|minimum|between)\b",
        re.IGNORECASE,
    )
    _TABLE = re.compile(
        r"\b(?:table|column|row|spreadsheet|dataset)\b",
        re.IGNORECASE,
    )
    _MULTI_SOURCE = re.compile(
        r"\b(?:sources?|both|each|across|multiple|several|respectively)\b",
        re.IGNORECASE,
    )
    _ENUMERATION = re.compile(
        r"\b(?:list|enumerate|which|what are|identify all|how many)\b",
        re.IGNORECASE,
    )
    _NUMERICAL = re.compile(
        r"\b(?:calculate|compute|difference|sum|average|mean|median|percent|"
        r"percentage|increase|decrease|largest|smallest|count)\b",
        re.IGNORECASE,
    )
    _DOCUMENT = re.compile(
        r"\b(?:report|paper|document|standard|regulation|law|dataset|record|"
        r"filing|publication|manual|specification)\b",
        re.IGNORECASE,
    )
    _UNCERTAINTY = re.compile(
        r"\b(?:latest|current|recent|approximately|estimate|conflicting|"
        r"controversial|uncertain|according to)\b",
        re.IGNORECASE,
    )
    _WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

    def __init__(
        self,
        task_text: str,
        *,
        fast: bool,
        structured_output: bool,
        output_fields: Sequence[str] = (),
        started: float | None = None,
        time_limit_seconds: float = 300.0,
        final_reserve_seconds: float = 12.0,
        remaining_cost_usd: float | None = None,
        minimum_cost_reserve_usd: float = 0.005,
        max_materialized_citation_chars: int = 80000,
    ) -> None:
        self.task_text = " ".join((task_text or "").split()).strip()
        self.fast = bool(fast)
        self.output_fields = tuple(
            str(item).strip()
            for item in output_fields
            if str(item).strip()
        )
        self.profile = self._classify(
            self.task_text,
            structured_output=structured_output,
        )
        self.depth = self._select_depth()
        self.plan = self._build_plan()
        self.ledger = EvidenceLedger()
        self.providers: dict[str, ProviderHealth] = {}
        self.stage = ResearchStage.ANALYZE
        self.stop_reason: str | None = None
        self.repair_used = False
        self.last_confidence = ConfidenceComponents()
        self.deterministic_solver_used: str | None = None
        self._last_evidence_count = 0
        self._saturation_rounds = 0

        started_at = (
            time.monotonic()
            if started is None
            else float(started)
        )
        max_rounds = 2 if fast else 3
        max_search = 3 if fast else 5
        max_fetch = 6 if fast else 10
        max_llm = 2 if fast else 4

        self.budget = ResearchBudget(
            started=started_at,
            time_limit_seconds=max(1.0, float(time_limit_seconds)),
            final_reserve_seconds=max(
                1.0,
                float(final_reserve_seconds),
            ),
            max_rounds=max_rounds,
            max_search_calls=max_search,
            max_fetch_calls=max_fetch,
            max_llm_calls=max_llm,
            max_materialized_citation_chars=int(
                max_materialized_citation_chars
            ),
            minimum_cost_reserve_usd=max(
                0.0,
                float(minimum_cost_reserve_usd),
            ),
            remaining_cost_usd=remaining_cost_usd,
        )

    def _classify(
        self,
        text: str,
        *,
        structured_output: bool,
    ) -> TaskProfile:
        lower = text.lower()

        temporal = bool(self._TEMPORAL.search(lower))
        comparative = bool(self._COMPARATIVE.search(lower))
        table = bool(self._TABLE.search(lower))
        multi_source = bool(self._MULTI_SOURCE.search(lower))
        enumeration = bool(self._ENUMERATION.search(lower))
        numerical = bool(self._NUMERICAL.search(lower))
        document = bool(self._DOCUMENT.search(lower))
        uncertainty = bool(self._UNCERTAINTY.search(lower))

        deterministic = bool(
            numerical
            or (comparative and table)
            or (
                structured_output
                and comparative
            )
        )

        return TaskProfile(
            factual=True,
            temporal=temporal,
            comparative=comparative,
            table=table,
            multi_source=(
                multi_source
                or comparative
            ),
            document_extraction=document,
            enumeration=enumeration,
            numerical=numerical,
            structured_output=structured_output,
            evidence_required=True,
            high_uncertainty=uncertainty,
            conflict_risk=(
                multi_source
                or uncertainty
                or comparative
            ),
            deterministic_operation=deterministic,
        )

    def _select_depth(self) -> ResearchDepth:
        complexity = sum(
            int(value)
            for value in (
                self.profile.temporal,
                self.profile.comparative,
                self.profile.multi_source,
                self.profile.document_extraction,
                self.profile.high_uncertainty,
                self.profile.table,
            )
        )

        if self.fast:
            return (
                ResearchDepth.STANDARD
                if complexity >= 3
                else ResearchDepth.LIGHT
            )

        if complexity >= 4:
            return ResearchDepth.DEEP

        if complexity >= 2:
            return ResearchDepth.STANDARD

        return ResearchDepth.LIGHT

    @staticmethod
    def _keywords(text: str, *, limit: int = 10) -> list[str]:
        stop = {
            "about", "after", "against", "also", "and", "are", "between",
            "both", "could", "each", "for", "from", "have", "into", "most",
            "not", "only", "other", "over", "same", "than", "that", "the",
            "their", "then", "there", "these", "they", "this", "those",
            "through", "under", "using", "was", "were", "what", "when",
            "where", "which", "while", "with", "would",
        }
        tokens = []
        for token in SLAIResearchRuntime._WORD.findall(text.lower()):
            if (
                len(token) < 4
                or token in stop
                or token in tokens
            ):
                continue
            tokens.append(token)
        return tokens[:limit]

    def _build_plan(self) -> ResearchPlan:
        claims = [
            ClaimRequirement(
                "answer_fact",
                "core factual answer",
                required_sources=1,
            )
        ]

        if self.profile.temporal:
            claims.append(
                ClaimRequirement(
                    "temporal_anchor",
                    "requested date/version/report anchor",
                    required_sources=1,
                )
            )

        if self.profile.multi_source:
            claims.append(
                ClaimRequirement(
                    "source_coverage",
                    "independent source coverage",
                    required_sources=2,
                )
            )

        if self.profile.comparative:
            claims.append(
                ClaimRequirement(
                    "comparison_result",
                    "requested comparison result",
                    required_sources=2,
                )
            )

        if self.profile.enumeration:
            claims.append(
                ClaimRequirement(
                    "enumeration_coverage",
                    "requested list or exhaustive set",
                    required_sources=1,
                )
            )

        if self.profile.structured_output and self.output_fields:
            for field_name in self.output_fields:
                claims.append(
                    ClaimRequirement(
                        "field:" + field_name,
                        "structured output field " + field_name,
                        required_sources=1,
                    )
                )

        queries = [self.task_text[:320]] if self.task_text else []

        keywords = self._keywords(self.task_text)
        if self.profile.multi_source and keywords:
            queries.append(
                " ".join(keywords[:8])
                + " primary source"
            )
        if self.profile.temporal and keywords:
            queries.append(
                " ".join(keywords[:8])
                + " exact date version"
            )

        deduped = []
        for query in queries:
            normalized = " ".join(query.split()).strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized[:320])

        solver = None
        if self.profile.table and self.profile.comparative:
            solver = "table_comparison"
        elif self.profile.numerical:
            solver = "numeric_operation"

        return ResearchPlan(
            claims=claims,
            initial_queries=deduped[:3],
            stop_conditions=(
                "required claims supported",
                "budget exhausted",
                "time reserve reached",
                "evidence saturated",
            ),
            preferred_source_count=(
                2 if self.profile.multi_source else 1
            ),
            deterministic_solver=solver,
        )

    def analyze(self) -> TaskProfile:
        self.stage = ResearchStage.ANALYZE
        return self.profile

    def planning_snapshot(self) -> ResearchPlan:
        self.stage = ResearchStage.PLAN
        return self.plan

    def update_remaining_cost(self, remaining_cost_usd: float | None) -> None:
        if remaining_cost_usd is not None:
            self.budget.remaining_cost_usd = float(
                remaining_cost_usd
            )

    def record_search(self, count: int = 1) -> None:
        self.budget.search_calls += max(0, int(count))

    def record_fetch(self, count: int = 1) -> None:
        self.budget.fetch_calls += max(0, int(count))

    def record_llm(self, count: int = 1) -> None:
        self.budget.llm_calls += max(0, int(count))

    def record_citation_chars(self, count: int) -> None:
        self.budget.materialized_citation_chars += max(
            0,
            int(count),
        )

    def mark_provider(
        self,
        provider: str,
        *,
        success: bool = False,
        error: str | None = None,
    ) -> ProviderHealth:
        key = (provider or "unknown").strip().lower()
        health = self.providers.setdefault(
            key,
            ProviderHealth(),
        )

        if success:
            health.successes += 1
            health.status = ProviderStatus.HEALTHY
            health.last_error = None
            return health

        health.failures += 1
        health.last_error = (
            str(error)[:160]
            if error
            else "unknown failure"
        )
        message = (error or "").lower()

        if any(
            token in message
            for token in (
                "credential unavailable",
                "api key",
                "unauthorized",
                "authentication",
            )
        ):
            health.status = ProviderStatus.CREDENTIAL_UNAVAILABLE
        elif "rate" in message and "limit" in message:
            health.status = ProviderStatus.RATE_LIMITED
        elif "timeout" in message:
            health.status = ProviderStatus.TIMEOUT_PRONE
        elif health.failures >= 2:
            health.status = ProviderStatus.HARD_FAILURE

        return health

    def provider_usable(self, provider: str) -> bool:
        health = self.providers.get(
            (provider or "").strip().lower()
        )
        return True if health is None else health.usable

    @staticmethod
    def _authority_from_domain(domain: str) -> float:
        value = (domain or "").lower()
        if (
            value.endswith(".gov")
            or value.endswith(".gov.uk")
            or value.endswith(".edu")
            or value.endswith(".ac.uk")
            or value.endswith(".europa.eu")
        ):
            return 1.0
        if any(
            token in value
            for token in (
                "who.int",
                "oecd.org",
                "worldbank.org",
                "nasa.gov",
                "usgs.gov",
                "nist.gov",
            )
        ):
            return 0.95
        if value:
            return 0.65
        return 0.25

    def _claim_support_for_record(
        self,
        record: EvidenceRecord,
    ) -> set[str]:
        text = (
            record.title
            + "\n"
            + record.excerpt
            + "\n"
            + record.url
        ).lower()

        query_terms = set(self._keywords(self.task_text))
        evidence_terms = set(self._keywords(text, limit=80))
        overlap = (
            len(query_terms & evidence_terms)
            / max(1, len(query_terms))
        )

        supported = set()

        if overlap >= 0.18 or record.relevance >= 0.45:
            supported.add("answer_fact")

        if self.profile.temporal:
            years = set(
                re.findall(r"\b20\d{2}\b", self.task_text)
            )
            if not years or any(year in text for year in years):
                supported.add("temporal_anchor")

        if self.profile.multi_source and (
            overlap >= 0.12
            or record.relevance >= 0.35
        ):
            supported.add("source_coverage")

        if self.profile.comparative and (
            overlap >= 0.18
            or record.relevance >= 0.50
        ):
            supported.add("comparison_result")

        if self.profile.enumeration and (
            overlap >= 0.18
            or record.relevance >= 0.50
        ):
            supported.add("enumeration_coverage")

        for field_name in self.output_fields:
            tokens = self._keywords(
                field_name.replace("_", " "),
                limit=4,
            )
            if not tokens or any(token in text for token in tokens):
                supported.add("field:" + field_name)

        return supported

    def add_evidence(
        self,
        record: EvidenceRecord,
    ) -> tuple[EvidenceRecord, bool]:
        if record.authority <= 0.0:
            record.authority = self._authority_from_domain(
                record.domain
            )

        if not record.supported_claims:
            record.supported_claims = self._claim_support_for_record(
                record
            )

        stored, added = self.ledger.add(record)
        self._refresh_claim_states()

        return stored, added

    def _refresh_claim_states(self) -> None:
        for claim in self.plan.claims:
            source_ids = self.ledger.source_ids_for_claim(
                claim.claim_id
            )
            claim.source_ids = source_ids

            if claim.conflicting_source_ids:
                claim.state = ClaimState.CONFLICTING
            elif len(source_ids) >= claim.required_sources:
                claim.state = ClaimState.SUPPORTED
            elif source_ids:
                claim.state = ClaimState.PARTIAL
            else:
                claim.state = ClaimState.MISSING

    def mark_conflict(
        self,
        claim_id: str,
        source_ids: Iterable[str],
    ) -> None:
        for claim in self.plan.claims:
            if claim.claim_id != claim_id:
                continue
            claim.conflicting_source_ids.update(
                str(item)
                for item in source_ids
            )
            claim.state = ClaimState.CONFLICTING
            break

    def unresolved_claims(self) -> list[ClaimRequirement]:
        self._refresh_claim_states()
        return [
            claim
            for claim in self.plan.claims
            if claim.state != ClaimState.SUPPORTED
        ]

    def claim_coverage(self) -> float:
        self._refresh_claim_states()

        if not self.plan.claims:
            return 1.0

        score = 0.0
        for claim in self.plan.claims:
            if claim.state == ClaimState.SUPPORTED:
                score += 1.0
            elif claim.state == ClaimState.PARTIAL:
                score += 0.5

        return score / len(self.plan.claims)

    def confidence(
        self,
        *,
        citation_support: float | None = None,
        schema_valid: bool = True,
        deterministic_consistent: bool = True,
    ) -> ConfidenceComponents:
        records = self.ledger.records

        authority = (
            sum(record.authority for record in records)
            / len(records)
            if records
            else 0.0
        )
        temporal = (
            sum(record.temporal_match for record in records)
            / len(records)
            if records
            else (0.0 if self.profile.temporal else 1.0)
        )
        conflicts = sum(
            1
            for claim in self.plan.claims
            if claim.state == ClaimState.CONFLICTING
        )
        agreement = max(
            0.0,
            1.0 - conflicts / max(1, len(self.plan.claims)),
        )
        citation = (
            min(
                1.0,
                len(
                    [
                        record
                        for record in records
                        if record.citation_eligible
                    ]
                )
                / max(
                    1,
                    self.plan.preferred_source_count,
                ),
            )
            if citation_support is None
            else max(0.0, min(1.0, citation_support))
        )

        self.last_confidence = ConfidenceComponents(
            claim_coverage=self.claim_coverage(),
            source_authority=authority,
            temporal_match=temporal,
            source_agreement=agreement,
            deterministic_consistency=(
                1.0 if deterministic_consistent else 0.0
            ),
            citation_support=citation,
            schema_validity=(
                1.0 if schema_valid else 0.0
            ),
        )
        return self.last_confidence

    def evidence_saturated(self) -> bool:
        count = len(self.ledger.records)

        if count <= self._last_evidence_count:
            self._saturation_rounds += 1
        else:
            self._saturation_rounds = 0

        self._last_evidence_count = count
        return self._saturation_rounds >= 1

    def follow_up_queries(self) -> list[str]:
        unresolved = self.unresolved_claims()
        if not unresolved:
            return []

        keywords = self._keywords(self.task_text, limit=9)
        base = " ".join(keywords) or self.task_text[:220]
        queries = []

        for claim in unresolved[:2]:
            suffix = claim.description

            if claim.state == ClaimState.CONFLICTING:
                suffix += " primary authoritative source verify conflict"
            elif claim.claim_id == "temporal_anchor":
                suffix += " exact date version"
            elif claim.claim_id == "source_coverage":
                suffix += " independent primary source"
            else:
                suffix += " evidence"

            query = " ".join((base + " " + suffix).split())[:320]
            if query and query not in queries:
                queries.append(query)

        return queries

    def should_continue_research(
        self,
        *,
        now: float | None = None,
    ) -> ResearchDecision:
        self.stage = ResearchStage.ASSESS_EVIDENCE

        unresolved = self.unresolved_claims()
        confidence = self.confidence()

        if not unresolved and confidence.aggregate >= 0.72:
            self.stop_reason = "required_claims_supported"
            return ResearchDecision(
                False,
                self.stop_reason,
            )

        if not self.budget.can_round(now):
            self.stop_reason = "research_budget_exhausted"
            return ResearchDecision(
                False,
                self.stop_reason,
            )

        if self.evidence_saturated() and self.budget.rounds > 0:
            self.stop_reason = "evidence_saturated"
            return ResearchDecision(
                False,
                self.stop_reason,
            )

        queries = self.follow_up_queries()
        if not queries:
            self.stop_reason = "no_actionable_gap"
            return ResearchDecision(
                False,
                self.stop_reason,
            )

        self.stage = ResearchStage.IDENTIFY_GAPS
        return ResearchDecision(
            True,
            "unresolved_claims",
            queries,
        )

    def begin_round(self, *, follow_up: bool = False) -> bool:
        if not self.budget.can_round():
            return False

        self.budget.rounds += 1
        self.stage = (
            ResearchStage.FOLLOW_UP_RETRIEVAL
            if follow_up
            else ResearchStage.RETRIEVE
        )
        return True

    def can_repair(self) -> bool:
        return (
            not self.repair_used
            and self.budget.final_reserve_intact()
            and self.budget.cost_reserve_intact()
            and self.budget.can_search()
        )

    def verification_decision(
        self,
        candidate: Any,
        *,
        schema_valid: bool = True,
        citation_count: int = 0,
        deterministic_consistent: bool = True,
    ) -> ResearchDecision:
        self.stage = ResearchStage.VERIFY

        empty = (
            candidate is None
            or candidate == ""
            or candidate == {}
            or candidate == []
        )
        citation_support = min(
            1.0,
            citation_count
            / max(1, self.plan.preferred_source_count),
        )
        confidence = self.confidence(
            citation_support=citation_support,
            schema_valid=schema_valid,
            deterministic_consistent=deterministic_consistent,
        )

        problems = []
        if empty:
            problems.append("empty_candidate")
        if not schema_valid:
            problems.append("schema_invalid")
        if self.profile.evidence_required and citation_count <= 0:
            problems.append("missing_citations")
        if self.unresolved_claims():
            problems.append("claim_coverage")
        if confidence.aggregate < 0.62:
            problems.append("low_confidence")

        if not problems:
            self.stage = ResearchStage.FINALIZE
            self.stop_reason = "verification_passed"
            return ResearchDecision(
                False,
                self.stop_reason,
            )

        if self.can_repair():
            self.stage = ResearchStage.REPAIR
            self.repair_used = True
            return ResearchDecision(
                True,
                "repair:" + ",".join(problems),
                self.follow_up_queries(),
            )

        self.stop_reason = "verification_best_effort"
        return ResearchDecision(
            False,
            self.stop_reason,
        )

    def telemetry(self) -> dict[str, Any]:
        return {
            "task_profile": {
                "factual": self.profile.factual,
                "temporal": self.profile.temporal,
                "comparative": self.profile.comparative,
                "table": self.profile.table,
                "multi_source": self.profile.multi_source,
                "document_extraction": self.profile.document_extraction,
                "enumeration": self.profile.enumeration,
                "numerical": self.profile.numerical,
                "structured_output": self.profile.structured_output,
                "evidence_required": self.profile.evidence_required,
                "high_uncertainty": self.profile.high_uncertainty,
                "conflict_risk": self.profile.conflict_risk,
                "deterministic_operation": self.profile.deterministic_operation,
            },
            "research_depth": self.depth.value,
            "stage": self.stage.value,
            "rounds_executed": self.budget.rounds,
            "search_count": self.budget.search_calls,
            "fetch_count": self.budget.fetch_calls,
            "llm_count": self.budget.llm_calls,
            "provider_failures": {
                provider: {
                    "status": health.status.value,
                    "failures": health.failures,
                    "successes": health.successes,
                }
                for provider, health in sorted(
                    self.providers.items()
                )
                if health.failures
            },
            "evidence_count": len(self.ledger.records),
            "deduplicated_source_count": len(self.ledger.records),
            "unresolved_claims": [
                claim.claim_id
                for claim in self.unresolved_claims()
            ],
            "confidence": {
                "claim_coverage": self.last_confidence.claim_coverage,
                "source_authority": self.last_confidence.source_authority,
                "temporal_match": self.last_confidence.temporal_match,
                "source_agreement": self.last_confidence.source_agreement,
                "deterministic_consistency": self.last_confidence.deterministic_consistency,
                "citation_support": self.last_confidence.citation_support,
                "schema_validity": self.last_confidence.schema_validity,
                "aggregate": self.last_confidence.aggregate,
            },
            "deterministic_solver_used": self.deterministic_solver_used,
            "citation_materialized_character_estimate": (
                self.budget.materialized_citation_chars
            ),
            "stop_reason": self.stop_reason,
        }
# ARTIFACT_RUNTIME_END
