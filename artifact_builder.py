"""Deterministic exporter for standalone Harnyx miner artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pprint
import re

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils.config_loader import get_config_section, load_config
from .utils.miner_errors import ArtifactBuildError, ArtifactValidationError
from .utils.miner_helpers import PROJECT_ROOT, git_head, require_external_repository, run_checked

_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "harnyx"
_TEMPLATE = _ARTIFACT_ROOT / "_agent_template.py.tmpl"
_BASELINE = _ARTIFACT_ROOT / "baseline_agent.py"
_MANIFEST_ROOT = PROJECT_ROOT / "benchmarks" / "harnyx" / "manifests"
_FILENAMES = {
    "b0": "baseline_agent.py",
    "b1": "b1_agent.py",
    "b2": "b2_agent.py",
    "b3": "b3_agent.py",
    "b4": "b4_agent.py",
}
_ABLATIONS = {
    "provider_routing",
    "decomposition",
    "retrieval",
    "evidence_ranking",
    "verification",
}
_SECRET = re.compile(
    r"(?i)(api[_-]?key|seed phrase|mnemonic|private[_-]?key|hotkey_uri)"
    r"\s*[=:]\s*['\"][^'\"]+['\"]"
)
_FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "globals",
    "locals",
    "vars",
    "dir",
    "type",
    "help",
    "__import__",
    "setattr",
    "delattr",
}
_FORBIDDEN_IMPORTS = {"importlib", "inspect"}
_FORBIDDEN_STMTS = (ast.Global, ast.Nonlocal, ast.Delete, ast.Match)
_FORBIDDEN_ATTRS = {
    "__dict__",
    "__code__",
    "__globals__",
    "__mro__",
    "__subclasses__",
}


@dataclass(frozen=True, slots=True)
class ArtifactBuildResult:
    profile: str
    path: Path
    sha256: str
    size_bytes: int
    manifest_path: Path
    official_validation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "manifest_path": str(self.manifest_path),
            "official_validation": self.official_validation,
        }


def build_artifact(
    profile_name: str,
    *,
    output_path: str | Path | None = None,
    official_validate: bool = False,
    disabled_components: Sequence[str] = (),
    manifest_root: str | Path | None = None,
) -> ArtifactBuildResult:
    profile_name = profile_name.strip().lower()
    if profile_name not in _FILENAMES:
        raise ArtifactBuildError(
            "unknown artifact profile",
            context={"profile": profile_name, "supported": sorted(_FILENAMES)},
        )

    unknown = sorted(set(disabled_components) - _ABLATIONS)
    if unknown:
        raise ArtifactBuildError(
            "unknown ablation component",
            context={"components": unknown},
        )
    if profile_name == "b0" and disabled_components:
        raise ArtifactBuildError("B0 has no optional components to ablate")

    config = load_config()
    artifact_config = dict(get_config_section("artifact", config=config))
    profiles = artifact_config.pop("profiles", {})
    settings = profiles.get(profile_name) if isinstance(profiles, Mapping) else None
    if not isinstance(settings, Mapping):
        raise ArtifactBuildError(
            "artifact profile is missing from configs/harnyx.yaml",
            context={"profile": profile_name},
        )

    profile = _profile(profile_name, artifact_config, settings)
    for component in disabled_components:
        profile[component] = False

    # B0 is intentionally a small hand-auditable reference artifact. Its checked-in
    # file is the canonical source. B1-B4 are compiled from the selective template.
    source = _baseline_source() if profile_name == "b0" else _render_template(profile)
    _preflight(source)
    data = source.encode("utf-8")
    maximum = _max_agent_bytes()
    if len(data) > maximum:
        raise ArtifactValidationError(
            "generated artifact exceeds Harnyx MAX_AGENT_BYTES",
            context={"size_bytes": len(data), "max_bytes": maximum},
        )
    digest = hashlib.sha256(data).hexdigest()

    path = _resolve_output_path(profile_name, output_path, disabled_components)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not rewrite the canonical B0 source when it already is the requested path.
    if path != _BASELINE.resolve() or data != path.read_bytes():
        path.write_bytes(data)

    validated = False
    if official_validate:
        official = official_validate_artifact(path)
        if official != digest:
            raise ArtifactValidationError(
                "official Harnyx hash differs from Miner hash",
                context={"miner_sha256": digest, "harnyx_sha256": official},
            )
        validated = True

    manifests = (
        Path(manifest_root).expanduser().resolve()
        if manifest_root is not None
        else _MANIFEST_ROOT
    )
    manifest = _write_manifest(
        manifests,
        profile_name,
        profile,
        path,
        digest,
        len(data),
        maximum,
        validated,
        disabled_components,
    )
    return ArtifactBuildResult(
        profile_name,
        path,
        digest,
        len(data),
        manifest,
        validated,
    )


def build_all(*, official_validate: bool = False) -> list[ArtifactBuildResult]:
    return [
        build_artifact(name, official_validate=official_validate)
        for name in _FILENAMES
    ]


def official_validate_artifact(path: str | Path) -> str:
    harnyx = require_external_repository(
        "harnyx",
        "miner/src/harnyx_miner/agent_source.py",
    )
    command = [
        "uv",
        "run",
        "--frozen",
        "--package",
        "harnyx-miner",
        "python",
        "-c",
        (
            "import sys; from pathlib import Path; "
            "from harnyx_miner.agent_source import "
            "agent_sha256,load_submittable_agent_bytes; "
            "data=load_submittable_agent_bytes(Path(sys.argv[1])); "
            "print(agent_sha256(data))"
        ),
        str(Path(path).expanduser().resolve()),
    ]
    completed = run_checked(command, cwd=harnyx, timeout=120)
    digest = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ArtifactValidationError(
            "official Harnyx validation did not return a SHA-256 digest",
            context={"stdout_tail": completed.stdout[-500:]},
        )
    return digest


def harnyx_max_agent_bytes() -> int:
    """Return the active Harnyx artifact byte limit from pinned source."""
    return _max_agent_bytes()


def _baseline_source() -> str:
    try:
        return _BASELINE.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactBuildError(
            "unable to read canonical B0 baseline artifact",
            context={"path": str(_BASELINE)},
        ) from exc


def _render_template(profile: Mapping[str, Any]) -> str:
    try:
        template = _TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactBuildError(
            "unable to read artifact template",
            context={"path": str(_TEMPLATE)},
        ) from exc
    source = template.replace(
        "__PROFILE_JSON__",
        pprint.pformat(dict(profile), sort_dicts=True, width=120),
    )
    if "__PROFILE_JSON__" in source:
        raise ArtifactBuildError("artifact template substitution failed")
    return source


def _resolve_output_path(
    profile_name: str,
    output_path: str | Path | None,
    disabled_components: Sequence[str],
) -> Path:
    if output_path is not None:
        raw = Path(output_path).expanduser()
    elif disabled_components:
        raw = (
            _ARTIFACT_ROOT
            / "ablations"
            / (
                profile_name
                + "__minus_"
                + "_".join(sorted(disabled_components))
                + ".py"
            )
        )
    else:
        raw = _ARTIFACT_ROOT / _FILENAMES[profile_name]
    return raw.resolve() if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def _profile(
    name: str,
    base: Mapping[str, Any],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": name,
        "provider_routing": bool(settings.get("provider_routing", False)),
        "decomposition": bool(settings.get("decomposition", False)),
        "retrieval": bool(settings.get("retrieval", False)),
        "evidence_ranking": bool(settings.get("evidence_ranking", False)),
        "verification": bool(settings.get("verification", False)),
        "routes": [
            {
                "provider": str(base.get("llm_provider", "chutes")),
                "model": str(base.get("llm_model", "")),
            },
            {"provider": "openrouter", "model": "openai/gpt-oss-120b"},
            {"provider": "ai_gateway", "model": "openai/gpt-oss-120b"},
        ],
        "search_provider": str(base.get("search_provider", "desearch")),
        "fast_max_output_tokens": int(base.get("fast_max_output_tokens", 512)),
        "normal_max_output_tokens": int(base.get("normal_max_output_tokens", 1800)),
        "analysis_max_output_tokens": int(base.get("analysis_max_output_tokens", 700)),
        "verification_max_output_tokens": int(
            base.get("verification_max_output_tokens", 900)
        ),
        "search_results": int(base.get("search_results", 5)),
        "evidence_limit": int(base.get("evidence_limit", 5)),
        "tool_timeout_seconds": float(base.get("tool_timeout_seconds", 25.0)),
        "minimum_final_seconds": float(base.get("minimum_final_seconds", 12.0)),
        "reserve_budget_fraction": float(base.get("reserve_budget_fraction", 0.25)),
    }


def _max_agent_bytes() -> int:
    harnyx = require_external_repository(
        "harnyx",
        "packages/commons/src/harnyx_commons/sandbox/agent_staging.py",
    )
    path = harnyx / "packages/commons/src/harnyx_commons/sandbox/agent_staging.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "MAX_AGENT_BYTES"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, int) and value > 0:
            return value
    raise ArtifactValidationError(
        "unable to locate Harnyx MAX_AGENT_BYTES in pinned source"
    )


def _preflight(source: str) -> None:
    if _SECRET.search(source):
        raise ArtifactValidationError(
            "generated artifact appears to contain a secret literal"
        )
    try:
        tree = ast.parse(source, filename="generated_harnyx_agent.py")
        compile(source, "generated_harnyx_agent.py", "exec")
    except SyntaxError as exc:
        raise ArtifactValidationError("generated artifact is not valid Python") from exc

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_STMTS):
            violations.append(node.__class__.__name__)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_CALLS
        ):
            violations.append("call:" + node.func.id)
        elif isinstance(node, ast.Import):
            violations.extend(
                "import:" + alias.name
                for alias in node.names
                if alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORTS
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".", 1)[0] in _FORBIDDEN_IMPORTS
        ):
            violations.append("import:" + str(node.module))
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            violations.append("attribute:" + node.attr)
    if violations:
        raise ArtifactValidationError(
            "generated artifact violates documented Harnyx upload subset",
            context={"violations": sorted(set(violations))},
        )

    entries = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "query"
    ]
    if len(entries) != 1 or not isinstance(entries[0], ast.AsyncFunctionDef):
        raise ArtifactValidationError(
            "artifact must contain exactly one async query() definition"
        )


def _write_manifest(
    root: Path,
    name: str,
    profile: Mapping[str, Any],
    path: Path,
    digest: str,
    size: int,
    maximum: int,
    validated: bool,
    disabled: Sequence[str],
) -> Path:
    slai = require_external_repository("slai", "src/agents/agent_factory.py")
    harnyx = require_external_repository("harnyx", "packages/miner-sdk/pyproject.toml")
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{name}-{digest[:12]}.json"
    payload = {
        "schema": "slai-harnyx-artifact-manifest-v1",
        "profile": name,
        "strategy": dict(profile),
        "ablation": {"disabled_components": list(disabled)},
        "artifact_path": (
            str(path.relative_to(PROJECT_ROOT))
            if PROJECT_ROOT in path.parents
            else str(path)
        ),
        "sha256": digest,
        "size_bytes": size,
        "harnyx_max_agent_bytes": maximum,
        "official_harnyx_validation": validated,
        "commits": {
            "miner": git_head(PROJECT_ROOT),
            "slai": git_head(slai),
            "harnyx": git_head(harnyx),
        },
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build standalone Harnyx artifacts from Miner strategy profiles."
    )
    parser.add_argument("profile", choices=[*sorted(_FILENAMES), "all"])
    parser.add_argument("--official-validate", action="store_true")
    parser.add_argument("--output")
    parser.add_argument(
        "--disable",
        action="append",
        default=[],
        choices=sorted(_ABLATIONS),
    )
    args = parser.parse_args(argv)

    if args.profile == "all":
        if args.output or args.disable:
            parser.error("--output/--disable are valid only for one profile")
        result = [
            item.to_dict()
            for item in build_all(official_validate=args.official_validate)
        ]
    else:
        result = build_artifact(
            args.profile,
            output_path=args.output,
            official_validate=args.official_validate,
            disabled_components=tuple(args.disable),
        ).to_dict()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
