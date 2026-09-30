"""Repository and configured-path state shared by Miner services and orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config_loader import get_config_section, load_config
from .miner_errors import ExternalDependencyError, MinerConfigurationError
from .miner_helpers import PROJECT_ROOT, git_head, git_is_clean, require_external_repository

_EXTERNAL_SENTINELS: dict[str, str] = {
    "slai": "src/agents/agent_factory.py",
    "harnyx": "packages/miner-sdk/pyproject.toml",
}


def benchmark_database_path(config: Mapping[str, Any] | None = None) -> Path:
    resolved = dict(config) if config is not None else load_config()
    project = get_config_section("project", config=resolved)
    raw_path = str(project.get("results_database") or "").strip()
    if not raw_path:
        raise MinerConfigurationError("project.results_database must be configured")
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def repository_commits() -> dict[str, str]:
    roots = {
        name: require_external_repository(name, sentinel)
        for name, sentinel in _EXTERNAL_SENTINELS.items()
    }
    return {
        "miner": git_head(PROJECT_ROOT),
        "slai": git_head(roots["slai"]),
        "harnyx": git_head(roots["harnyx"]),
    }


def dependency_status(config: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    resolved = dict(config) if config is not None else load_config()
    external = get_config_section("external", config=resolved)
    result: dict[str, dict[str, Any]] = {}

    for name, sentinel in _EXTERNAL_SENTINELS.items():
        settings = external.get(name) or {}
        if not isinstance(settings, Mapping):
            raise MinerConfigurationError(
                f"external.{name} must be a mapping",
                context={"actual_type": type(settings).__name__},
            )
        expected = str(settings.get("expected_commit") or "").strip()
        try:
            root = require_external_repository(name, sentinel)
            actual = git_head(root)
            clean = git_is_clean(root)
        except ExternalDependencyError as exc:
            result[name] = {
                "status": "unavailable",
                "path": str(settings.get("path") or f"external/{name}"),
                "expected_commit": expected,
                "actual_commit": None,
                "revision_matches": False,
                "clean": False,
                "pinned": False,
                "detail": str(exc),
            }
            continue

        revision_matches = bool(expected and expected == actual)
        result[name] = {
            "status": "ready" if revision_matches and clean else "degraded",
            "path": str(root.relative_to(PROJECT_ROOT)),
            "expected_commit": expected,
            "actual_commit": actual,
            "revision_matches": revision_matches,
            "clean": clean,
            "pinned": revision_matches and clean,
        }

    miner_clean = git_is_clean(PROJECT_ROOT)
    result["miner"] = {
        "status": "ready" if miner_clean else "degraded",
        "actual_commit": git_head(PROJECT_ROOT),
        "clean": miner_clean,
    }
    return result
