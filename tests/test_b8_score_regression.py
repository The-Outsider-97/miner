from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_miner_package() -> None:
    if "miner" in sys.modules:
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
artifact_builder = importlib.import_module("miner.artifact_builder")
build_artifact = artifact_builder.build_artifact

_HELPERS = {
    "_normalize",
    "_split_markdown_row",
    "_split_tabular_row",
    "_parse_integer_cell",
    "_table_column_values",
    "_requested_comparison_column",
    "_deterministic_table_comparison",
    "_comparison_block",
    "_comparison_extrema",
    "_deterministic_output_from_evidence",
    "_first_markdown_table",
    "_first_tabular_table",
    "_focused_page_content",
}


class _Query:
    def __init__(self, output_schema):
        self.output_schema = output_schema


def _validate_output_against_schema(value, schema):
    assert isinstance(value, dict)
    required = set(schema.get("required", ()))
    assert required <= set(value)


def _load_helpers(source: str):
    parsed = ast.parse(source)
    selected = [
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and node.name in _HELPERS
    ]

    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        "re": re,
        "_SENTENCE": re.compile(r"(?<=[.!?])\s+"),
        "_YEAR_WEEK": re.compile(
            r"\b(20\d{2})[/-](\d{1,2})\b",
            re.IGNORECASE,
        ),
        "_MAX_PAGE_CHARS": 10000,
        "Query": _Query,
        "validate_output_against_schema": _validate_output_against_schema,
    }

    exec(
        compile(module, "b8_score_regression_helpers.py", "exec"),
        namespace,
    )
    return namespace


def _build_b8(tmp_path: Path) -> str:
    result = build_artifact(
        "b8",
        output_path=tmp_path / "b8_agent.py",
        manifest_root=tmp_path / "manifests",
    )
    return result.path.read_text(encoding="utf-8")


QUESTION = (
    'The UK Health Security Agency publishes weekly "NOIDs causative agents" '
    "reports for England. Compare only the first table of the report for week "
    "29 (week ending 18 July 2026) with the first table of the report for week "
    "30 (week ending 25 July 2026). Restrict attention to the single column "
    "for week 2026/29 which appears in both reports. For each agent compute "
    "the restatement as week-30 minus week-29. Treat a dash as zero and an "
    "agent row absent from one report as zero. Return the largest increase "
    "and largest decrease."
)

WEEK_29 = """HEADER\tWeek notification received\t2026/24\t2026/25\t2026/26\t2026/27\t2026/28\t2026/29
HEADER\tCampylobacter
ROW\tCampylobacter jejuni\t420\t387\t365\t440\t328\t268
ROW\tCampylobacter sp\t1,437\t1,235\t1,282\t1,476\t1,366\t1,253
HEADER\tSalmonella
ROW\tSalmonella enteritidis\t103\t94\t104\t104\t48\t15
ROW\tSalmonella sp\t35\t27\t23\t50\t203\t243
HEADER\tWeek notification received\t\t2026/24\t2026/25\t2026/26\t2026/27\t2026/28\t2026/29
HEADER\tTHIS IS A LATER TABLE AND MUST NOT BE USED
ROW\tCampylobacter jejuni\t0\t0\t0\t0\t0\t9999
"""

WEEK_30 = """HEADER\tWeek notification received\t2026/25\t2026/26\t2026/27\t2026/28\t2026/29\t2026/30
HEADER\tCampylobacter
ROW\tCampylobacter jejuni\t388\t365\t440\t332\t320\t282
ROW\tCampylobacter sp\t1,234\t1,282\t1,476\t1,363\t1,195\t1,400
HEADER\tSalmonella
ROW\tSalmonella enteritidis\t94\t104\t110\t102\t53\t42
ROW\tSalmonella sp\t27\t23\t40\t73\t167\t290
HEADER\tWeek notification received\t\t2026/25\t2026/26\t2026/27\t2026/28\t2026/29\t2026/30
HEADER\tTHIS IS A LATER TABLE AND MUST NOT BE USED
ROW\tSalmonella sp\t0\t0\t0\t0\t9999\t0
"""


def _schema():
    return {
        "type": "object",
        "properties": {
            "largest_increase_agent": {"type": "string"},
            "largest_increase_amount": {"type": "integer"},
            "largest_decrease_agent": {"type": "string"},
            "largest_decrease_amount": {"type": "integer"},
        },
        "required": [
            "largest_increase_agent",
            "largest_increase_amount",
            "largest_decrease_agent",
            "largest_decrease_amount",
        ],
        "additionalProperties": False,
    }


def test_b8_score_regression_ukhsa_exact_reference(tmp_path: Path):
    source = _build_b8(tmp_path)
    h = _load_helpers(source)

    focused_29 = h["_focused_page_content"](WEEK_29, QUESTION)
    focused_30 = h["_focused_page_content"](WEEK_30, QUESTION)

    assert "9999" not in focused_29
    assert "9999" not in focused_30

    rows_29 = h["_table_column_values"](focused_29, "2026/29")
    rows_30 = h["_table_column_values"](focused_30, "2026/29")

    assert rows_29["Campylobacter jejuni"] == 268
    assert rows_30["Campylobacter jejuni"] == 320
    assert rows_29["Salmonella sp"] == 243
    assert rows_30["Salmonella sp"] == 167

    comparison = h["_deterministic_table_comparison"](
        QUESTION,
        [{"content": focused_29}, {"content": focused_30}],
    )

    evidence = (
        comparison
        + "\n\nSOURCE 1\n"
        + focused_29
        + "\n\nSOURCE 2\n"
        + focused_30
    )

    output = h["_deterministic_output_from_evidence"](
        _Query(_schema()),
        evidence,
    )

    assert output == {
        "largest_decrease_agent": "Salmonella sp",
        "largest_decrease_amount": 76,
        "largest_increase_agent": "Campylobacter jejuni",
        "largest_increase_amount": 52,
    }


def test_b8_comparison_treats_missing_rows_as_zero(tmp_path: Path):
    source = _build_b8(tmp_path)
    h = _load_helpers(source)

    left = """HEADER\tWeek notification received\t2026/29
ROW\tDisappeared agent\t10
ROW\tStable agent\t5
HEADER\tWeek notification received\t2026/29
"""

    right = """HEADER\tWeek notification received\t2026/29
ROW\tAppeared agent\t12
ROW\tStable agent\t5
HEADER\tWeek notification received\t2026/29
"""

    comparison = h["_deterministic_table_comparison"](
        (
            "Compare the same week 2026/29 and identify "
            "the largest increase and largest decrease."
        ),
        [{"content": left}, {"content": right}],
    )

    assert (
        "Largest increase: Appeared agent = 0 -> 12 (change +12)."
        in comparison
    )
    assert (
        "Largest decrease: Disappeared agent = 10 -> 0 "
        "(change -10, magnitude 10)."
        in comparison
    )
