"""Thin Miner binding over SLAI's shared YAML configuration infrastructure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .miner_helpers import PROJECT_ROOT, prepend_import_path, require_external_repository

_SLAI_ROOT = require_external_repository("slai", "src/utils/configuration.py")
prepend_import_path(_SLAI_ROOT)

from src.utils.configuration import bind_config  # noqa: E402

_BINDING = bind_config(PROJECT_ROOT / "configs" / "harnyx.yaml")


def load_config(*, force_reload: bool = False, cache_ttl: float = 60.0) -> dict[str, Any]:
    return _BINDING.load(force_reload=force_reload, cache_ttl=cache_ttl)


def get_config_section(section_name: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _BINDING.section(section_name, config=config)


def reload_config() -> dict[str, Any]:
    return _BINDING.reload()


def config_cache_info() -> dict[str, Any]:
    return _BINDING.cache_info().to_dict()


def config_path() -> Path:
    return (PROJECT_ROOT / "configs" / "harnyx.yaml").resolve()
