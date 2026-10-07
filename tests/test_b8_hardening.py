from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_miner_package() -> None:
    existing = sys.modules.get("miner")

    if existing is not None:
        return

    spec = importlib.util.spec_from_file_location(
        "miner",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to bootstrap Miner package")

    package = importlib.util.module_from_spec(spec)
    sys.modules["miner"] = package
    spec.loader.exec_module(package)


_bootstrap_miner_package()

artifact_builder = importlib.import_module(
    "miner.artifact_builder",
)
build_artifact = artifact_builder.build_artifact


_HELPERS = {
    "_normalize",
    "_extract_years",
    "_normalize_anchor_text",
    "_temporal_anchors",
    "_candidate_weeks",
    "_span_distance",
    "_report_anchor_for_week",
    "_candidate_matches_anchors",
    "_strip_temporal_anchors",
    "_query_for_week",
    "_matches_exact_week",
    "_matches_report_anchor",
    "_comparison_block",
    "_comparison_extrema",
    "_comparison_ranked_rows",
    "_comparison_support_labels",
    "_context_slice",
    "_merge_citation_slices",
    "_requested_comparison_column",
    "_deterministic_output_from_evidence",
    "_comparison_note",
}


@dataclass(frozen=True)
class _CitationSlice:
    start: int
    end: int


class _Query:
    def __init__(self, output_schema):
        self.output_schema = output_schema


def _validate_output_against_schema(value, schema):
    assert isinstance(value, dict)

    required = set(
        schema.get(
            "required",
            (),
        )
    )

    assert required <= set(value)


def _load_b8_helpers(source: str):
    parsed = ast.parse(source)

    selected = [
        node
        for node in parsed.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name in _HELPERS
        )
    ]

    module = ast.Module(
        body=selected,
        type_ignores=[],
    )
    ast.fix_missing_locations(module)

    namespace = {
        "CitationSlice": _CitationSlice,
        "Query": _Query,
        "_YEAR_WEEK": re.compile(
            r"\b(20\d{2})[/-](\d{1,2})\b",
            re.IGNORECASE,
        ),
        "_WEEK": re.compile(
            r"\bweek\s+(\d{1,2})\b",
            re.IGNORECASE,
        ),
        "_DATE": re.compile(
            r"\b\d{1,2}\s+"
            r"(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+20\d{2}\b",
            re.IGNORECASE,
        ),
        "_SENTENCE": re.compile(
            r"(?<=[.!?])\s+",
        ),
        "_MIN_CITATION_SLICE_CHARS": 100,
        "_TARGET_CITATION_SLICE_CHARS": 260,
        "_MAX_COMPARISON_CITATION_SLICES": 6,
        "re": re,
        "validate_output_against_schema": (
            _validate_output_against_schema
        ),
    }

    exec(
        compile(
            module,
            "b8_helper_contract.py",
            "exec",
        ),
        namespace,
    )

    return namespace


def _build_b8(tmp_path: Path):
    result = build_artifact(
        "b8",
        output_path=tmp_path / "b8_agent.py",
        manifest_root=tmp_path / "manifests",
    )

    return result.path.read_text(
        encoding="utf-8",
    )


def _uk_noids_question() -> str:
    return (
        "Compare the UK Health Security Agency NOIDs causative agents "
        "week 29 report (week ending 18 July 2026) with the week 30 "
        "report (week ending 25 July 2026). Restrict attention to the "
        "single column for week 2026/29 that appears in both reports "
        "and identify the largest increase and largest decrease."
    )


def test_b8_maps_each_report_week_to_its_exact_date_and_year(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)
    question = _uk_noids_question()

    week_29 = helpers["_report_anchor_for_week"](
        question,
        29,
    )
    week_30 = helpers["_report_anchor_for_week"](
        question,
        30,
    )

    assert week_29 == {
        "week": 29,
        "date": "18 july 2026",
        "year": "2026",
    }
    assert week_30 == {
        "week": 30,
        "date": "25 july 2026",
        "year": "2026",
    }


def test_b8_rejects_same_week_from_wrong_year(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)
    question = _uk_noids_question()

    wrong = (
        "Noids Report 2022 Week 29 - 32 - National Data Library "
        "https://www.data.gov.uk/dataset/example/noids-report-2022-week-29"
    )
    correct = (
        "NOIDs causative agents: week 29 "
        "(week ending 18 July 2026) - GOV.UK "
        "https://www.gov.uk/government/publications/"
        "notifiable-diseases-causative-agents-reports-for-2026/"
        "noids-causative-agents-week-29-week-ending-18-july-2026"
    )

    assert not helpers["_matches_report_anchor"](
        wrong,
        question,
        29,
    )
    assert helpers["_matches_report_anchor"](
        correct,
        question,
        29,
    )


def test_b8_week_queries_preserve_exact_report_date_and_year(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)
    question = _uk_noids_question()

    week_29 = helpers["_query_for_week"](
        question,
        29,
    ).lower()
    week_30 = helpers["_query_for_week"](
        question,
        30,
    ).lower()

    assert '"week 29"' in week_29
    assert '"18 july 2026"' in week_29
    assert '"2026/29"' in week_29

    assert '"week 30"' in week_30
    assert '"25 july 2026"' in week_30
    assert '"2026/30"' in week_30


def test_b8_identifies_explicit_shared_comparison_column(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)

    assert (
        helpers["_requested_comparison_column"](
            _uk_noids_question(),
        )
        == "2026/29"
    )


def test_b8_citation_slices_satisfy_harnyx_minimum(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)

    text = (
        ("x" * 180)
        + "\nHEADER\tWeek notification received\t2026/29\t2026/30\n"
        + ("y" * 220)
        + "\nROW\tCampylobacter jejuni\t268\t320\n"
        + ("z" * 220)
        + "\nROW\tSalmonella sp\t243\t167\n"
        + ("q" * 220)
    )

    for needle in (
        "Week notification received",
        "Campylobacter jejuni",
        "Salmonella sp",
    ):
        segment = helpers["_context_slice"](
            text,
            needle,
        )

        assert segment is not None
        assert (
            0
            <= segment.start
            < segment.end
            <= len(text)
        )
        assert (
            segment.end - segment.start
            >= 100
        )


def test_b8_deterministic_comparison_output_and_note(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)
    helpers = _load_b8_helpers(source)

    evidence = """DETERMINISTIC TABLE COMPARISON
Compared column 2026/29 across SOURCE 1 and SOURCE 2 by exact row label.
Largest increase: Campylobacter jejuni = 268 -> 320 (change +52).
Largest decrease: Salmonella sp = 243 -> 167 (change -76, magnitude 76).
Top increases:
- Campylobacter jejuni: 268 -> 320 (+52)
- Salmonella enteritidis: 15 -> 53 (+38)
Top decreases:
- Salmonella sp: 243 -> 167 (-76)
- Campylobacter sp: 1253 -> 1195 (-58)

SOURCE 1
SOURCE 2
"""

    schema = {
        "type": "object",
        "required": [
            "largest_decrease_agent",
            "largest_decrease_amount",
            "largest_increase_agent",
            "largest_increase_amount",
        ],
    }

    output = helpers[
        "_deterministic_output_from_evidence"
    ](
        _Query(schema),
        evidence,
    )

    assert output == {
        "largest_decrease_agent": "Salmonella sp",
        "largest_decrease_amount": 76,
        "largest_increase_agent": "Campylobacter jejuni",
        "largest_increase_amount": 52,
    }

    note = helpers["_comparison_note"](
        evidence,
        2,
        _uk_noids_question(),
    )

    assert note is not None
    assert "Report week 29, 2026/29" in note
    assert "Campylobacter jejuni 268" in note
    assert "Salmonella sp 243" in note
    assert (
        "Report week 30 restatement of 2026/29"
        in note
    )
    assert "Campylobacter jejuni 320" in note
    assert "Salmonella sp 167" in note
    assert "Salmonella enteritidis (+38)" in note
    assert "Campylobacter sp (-58)" in note
    assert "[[1]][[2]]" in note


def test_b8_has_deterministic_pre_llm_fast_path(
    tmp_path: Path,
):
    source = _build_b8(tmp_path)

    deterministic = source.index(
        "deterministic_output = "
        "_deterministic_output_from_evidence("
    )
    first_chat_after_evidence = source.index(
        "raw, updated = await _chat(",
        deterministic,
    )

    assert deterministic < first_chat_after_evidence
    assert (
        "if deterministic_output is not None:"
        in source[
            deterministic:first_chat_after_evidence
        ]
    )
