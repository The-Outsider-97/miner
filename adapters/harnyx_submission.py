"""Official Harnyx artifact-upload boundary."""

from __future__ import annotations

import json
import os
import re

from pathlib import Path
from typing import Any

from ..utils.config_loader import get_config_section
from ..utils.miner_errors import BenchmarkExecutionError, SubmissionError, SubmissionRejectedError
from ..utils.miner_helpers import require_external_repository, run_checked


def submission_configuration_status() -> dict[str, Any]:
    config = get_config_section("submission")

    required = {
        "platform": str(config.get("platform_base_url_env") or "PLATFORM_BASE_URL"),
        "wallet": str(config.get("wallet_name_env") or "HARNYX_WALLET_NAME"),
        "hotkey": str(config.get("hotkey_name_env") or "HARNYX_HOTKEY_NAME"),
    }

    missing = [
        env_name
        for env_name in required.values()
        if not os.getenv(env_name, "").strip()
    ]

    return {
        "ready": not missing,
        "missing_environment_variables": missing,
    }


def _required_environment() -> tuple[str, str, str]:
    config = get_config_section("submission")
    base_env = str(config.get("platform_base_url_env") or "PLATFORM_BASE_URL")
    wallet_env = str(config.get("wallet_name_env") or "HARNYX_WALLET_NAME")
    hotkey_env = str(config.get("hotkey_name_env") or "HARNYX_HOTKEY_NAME")

    base_url = os.getenv(base_env, "").strip()
    wallet = os.getenv(wallet_env, "").strip()
    hotkey = os.getenv(hotkey_env, "").strip()

    if not base_url or not wallet or not hotkey:
        raise SubmissionError(
            "Harnyx submission configuration is incomplete."
        )

    return base_url, wallet, hotkey


def _json_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue

        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(value, dict):
            return value

    raise SubmissionError("Harnyx submission returned no machine-readable result.")


def submit_agent(artifact_path: Path) -> dict[str, Any]:
    base_url, wallet_name, hotkey_name = (_required_environment())
    harnyx = require_external_repository("harnyx", "miner/src/harnyx_miner/submit.py")

    command = [
        "uv",
        "run",
        "--frozen",
        "--package",
        "harnyx-miner",
        "harnyx-miner-submit",
        "--agent-path",
        str(artifact_path.resolve()),
        "--wallet-name",
        wallet_name,
        "--hotkey-name",
        hotkey_name,
    ]

    try:
        completed = run_checked(
            command,
            cwd=harnyx,
            timeout=90,
            env_overrides={
                "PLATFORM_BASE_URL": base_url,
            },
        )

    except BenchmarkExecutionError as exc:
        stderr = str(exc.context.get("stderr_tail", ""))
        match = re.search(r"script upload failed \((\d{3})\)", stderr)

        if match is not None:
            status = int(match.group(1))
            if 400 <= status < 500:
                raise SubmissionRejectedError("Harnyx rejected the artifact submission.") from exc
        raise SubmissionError("Harnyx artifact submission failed.") from exc

    raw = _json_result(completed.stdout)

    allowed_keys = {
        "artifact_id",
        "content_hash",
        "submitted_at",
        "uid",
        "size_bytes",
    }

    result = {
        key: raw.get(key)
        for key in allowed_keys
        if key in raw
    }

    content_hash = result.get("content_hash")

    if not isinstance(content_hash, str):
        raise SubmissionError("Harnyx response did not include content_hash.")

    return result