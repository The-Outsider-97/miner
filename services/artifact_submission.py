"""Artifact discovery, preflight and explicit Harnyx submission."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..adapters.harnyx_submission import (
    submission_configuration_status,
    submit_agent,
)
from ..artifact_builder import (
    harnyx_max_agent_bytes,
    official_validate_artifact,
)
from ..utils.miner_errors import (
    MinerError,
    SubmissionConflictError,
    SubmissionError,
    SubmissionPreflightError,
)
from ..utils.miner_helpers import PROJECT_ROOT
from ..utils.repository_state import dependency_status
from .submission_ledger import SubmissionLedger

_ARTIFACT_ROOT = (
    PROJECT_ROOT
    / "artifacts"
    / "harnyx"
).resolve()

_MANIFEST_ROOT = (
    PROJECT_ROOT
    / "benchmarks"
    / "harnyx"
    / "manifests"
).resolve()

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _read_manifest(
    path: Path,
) -> dict[str, Any] | None:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    return value if isinstance(value, dict) else None


def _artifact_path(
    manifest: dict[str, Any],
) -> Path:
    raw = manifest.get("artifact_path")

    if not isinstance(raw, str) or not raw.strip():
        raise SubmissionPreflightError(
            "Artifact manifest does not contain artifact_path."
        )

    candidate = Path(raw).expanduser()

    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate

    resolved = candidate.resolve()

    if (
        resolved == _ARTIFACT_ROOT
        or _ARTIFACT_ROOT not in resolved.parents
    ):
        raise SubmissionPreflightError(
            "Artifact path is outside the approved artifact directory."
        )

    return resolved


def _manifest_for_hash(
    artifact_hash: str,
) -> tuple[dict[str, Any], Path]:
    normalized = artifact_hash.lower().strip()

    if not _SHA256.fullmatch(normalized):
        raise SubmissionPreflightError(
            "Artifact SHA-256 is invalid."
        )

    if not _MANIFEST_ROOT.is_dir():
        raise SubmissionPreflightError(
            "No artifact manifests are available."
        )

    matches: list[
        tuple[str, dict[str, Any], Path]
    ] = []

    for path in _MANIFEST_ROOT.glob("*.json"):
        manifest = _read_manifest(path)

        if manifest is None:
            continue

        if (
            str(
                manifest.get("sha256")
                or ""
            ).lower()
            != normalized
        ):
            continue

        matches.append(
            (
                str(
                    manifest.get("built_at")
                    or ""
                ),
                manifest,
                path,
            )
        )

    if not matches:
        raise SubmissionPreflightError(
            "Artifact SHA-256 is not present in Miner manifests."
        )

    matches.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    _, manifest, manifest_path = matches[0]

    return manifest, manifest_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _has_query_entrypoint(
    path: Path,
) -> bool:
    try:
        source = path.read_text(
            encoding="utf-8",
        )

        tree = ast.parse(
            source,
            filename=str(path),
        )

    except (
        OSError,
        UnicodeDecodeError,
        SyntaxError,
    ):
        return False

    query_functions = [
        node
        for node in tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name == "query"
    ]

    return len(query_functions) == 1


def list_artifact_candidates() -> list[dict[str, Any]]:
    if not _MANIFEST_ROOT.is_dir():
        return []

    candidates: list[dict[str, Any]] = []

    with SubmissionLedger() as ledger:
        for path in _MANIFEST_ROOT.glob("*.json"):
            manifest = _read_manifest(path)

            if manifest is None:
                continue

            artifact_hash = str(
                manifest.get("sha256")
                or ""
            ).lower()

            if not _SHA256.fullmatch(
                artifact_hash
            ):
                continue

            try:
                artifact = _artifact_path(
                    manifest
                )
            except SubmissionPreflightError:
                continue

            previous = ledger.latest_upload(
                artifact_hash
            )

            candidates.append(
                {
                    "profile": manifest.get(
                        "profile"
                    ),
                    "version": manifest.get(
                        "profile"
                    ),
                    "sha256": artifact_hash,
                    "size_bytes": manifest.get(
                        "size_bytes"
                    ),
                    "built_at": manifest.get(
                        "built_at"
                    ),
                    "manifest_validated": bool(
                        manifest.get(
                            "official_harnyx_validation"
                        )
                    ),
                    "artifact_exists": (
                        artifact.is_file()
                    ),
                    "previous_upload": (
                        previous
                        if previous is not None
                        else None
                    ),
                }
            )

    candidates.sort(
        key=lambda item: str(
            item.get("built_at")
            or ""
        ),
        reverse=True,
    )

    return candidates


def preflight_artifact(
    artifact_hash: str,
) -> dict[str, Any]:
    manifest, _ = _manifest_for_hash(
        artifact_hash
    )

    path = _artifact_path(manifest)

    checks: list[dict[str, Any]] = []

    def add(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "detail": detail,
            }
        )

    exists = path.is_file()

    add(
        "artifact_exists",
        exists,
        (
            "Artifact exists."
            if exists
            else "Artifact file is missing."
        ),
    )

    expected_hash = str(
        manifest.get("sha256")
        or ""
    ).lower()

    actual_hash: str | None = None
    actual_size: int | None = None

    if exists:
        actual_hash = _sha256(path)
        actual_size = path.stat().st_size

    hash_matches = (
        actual_hash is not None
        and actual_hash == expected_hash
    )

    add(
        "sha256_matches_manifest",
        hash_matches,
        (
            "SHA-256 matches manifest."
            if hash_matches
            else "Artifact SHA-256 differs from manifest."
        ),
    )

    manifest_size = manifest.get(
        "size_bytes"
    )

    size_matches = (
        actual_size is not None
        and isinstance(
            manifest_size,
            int,
        )
        and actual_size == manifest_size
    )

    add(
        "size_matches_manifest",
        size_matches,
        (
            "Artifact size matches manifest."
            if size_matches
            else "Artifact size differs from manifest."
        ),
    )

    maximum = harnyx_max_agent_bytes()

    size_allowed = (
        actual_size is not None
        and actual_size <= maximum
    )

    add(
        "size_within_harnyx_limit",
        size_allowed,
        (
            f"Artifact is within the "
            f"{maximum}-byte Harnyx limit."
            if size_allowed
            else "Artifact exceeds the current Harnyx limit."
        ),
    )

    entrypoint = (
        exists
        and _has_query_entrypoint(
            path
        )
    )

    add(
        "query_entrypoint",
        entrypoint,
        (
            "Exactly one async query() entrypoint exists."
            if entrypoint
            else "Expected async query() entrypoint is invalid."
        ),
    )

    harnyx_pin = False

    try:
        state = dependency_status()
        harnyx = state.get(
            "harnyx",
            {},
        )

        harnyx_pin = bool(
            harnyx.get("pinned")
        )

    except MinerError:
        harnyx_pin = False

    add(
        "harnyx_revision",
        harnyx_pin,
        (
            "Pinned Harnyx revision is ready."
            if harnyx_pin
            else "Pinned Harnyx revision is unavailable or mismatched."
        ),
    )

    manifest_harnyx = str(
        (
            manifest.get("commits")
            or {}
        ).get("harnyx")
        or ""
    )

    current_harnyx = None

    try:
        current_harnyx = (
            dependency_status()
            .get(
                "harnyx",
                {},
            )
            .get("actual_commit")
        )
    except MinerError:
        current_harnyx = None

    manifest_revision_matches = bool(
        manifest_harnyx
        and current_harnyx
        and manifest_harnyx
        == current_harnyx
    )

    add(
        "manifest_harnyx_revision",
        manifest_revision_matches,
        (
            "Manifest Harnyx revision matches current pin."
            if manifest_revision_matches
            else "Manifest was built against a different Harnyx revision."
        ),
    )

    authentication = (
        submission_configuration_status()
    )

    add(
        "submission_configuration",
        bool(
            authentication.get(
                "ready"
            )
        ),
        (
            "Server-side submission configuration is present."
            if authentication.get("ready")
            else "Server-side Harnyx submission configuration is incomplete."
        ),
    )

    official_valid = False

    if (
        exists
        and hash_matches
        and size_matches
        and size_allowed
        and entrypoint
        and harnyx_pin
    ):
        try:
            official_hash = (
                official_validate_artifact(
                    path
                )
            )

            official_valid = (
                official_hash
                == expected_hash
            )

        except MinerError:
            official_valid = False

    add(
        "official_harnyx_validation",
        official_valid,
        (
            "Official Harnyx artifact validation passed."
            if official_valid
            else "Official Harnyx artifact validation failed."
        ),
    )

    with SubmissionLedger() as ledger:
        previous = ledger.latest_upload(
            expected_hash
        )

    eligible = all(
        bool(item["passed"])
        for item in checks
    )

    return {
        "eligible": eligible,
        "profile": manifest.get(
            "profile"
        ),
        "version": manifest.get(
            "profile"
        ),
        "sha256": expected_hash,
        "size_bytes": actual_size,
        "harnyx_max_bytes": maximum,
        "built_at": manifest.get(
            "built_at"
        ),
        "checks": checks,
        "duplicate_upload": (
            previous is not None
        ),
        "previous_upload": previous,
    }


def submit_artifact(
    artifact_hash: str,
    *,
    allow_resubmit: bool = False,
) -> dict[str, Any]:
    preflight = preflight_artifact(
        artifact_hash
    )

    if not preflight["eligible"]:
        raise SubmissionPreflightError(
            "Artifact preflight failed."
        )

    if (
        preflight["duplicate_upload"]
        and not allow_resubmit
    ):
        raise SubmissionConflictError(
            "This exact artifact hash was already uploaded. "
            "Explicit resubmission confirmation is required."
        )

    manifest, _ = _manifest_for_hash(
        artifact_hash
    )

    path = _artifact_path(manifest)

    with SubmissionLedger() as ledger:
        if not ledger.acquire_lock(
            artifact_hash
        ):
            raise SubmissionConflictError(
                "This artifact is already being submitted."
            )

        try:
            platform = submit_agent(path)

            content_hash = platform.get(
                "content_hash"
            )

            if (
                not isinstance(
                    content_hash,
                    str,
                )
                or content_hash.lower()
                != artifact_hash.lower()
            ):
                raise SubmissionError(
                    "Harnyx returned a different artifact hash."
                )

            artifact_id = platform.get(
                "artifact_id"
            )

            submitted_at = platform.get(
                "submitted_at"
            )

            uid = platform.get("uid")

            size_bytes = platform.get(
                "size_bytes"
            )

            ledger.record_upload(
                artifact_hash=artifact_hash,
                profile=str(
                    manifest.get(
                        "profile"
                    )
                    or ""
                ),
                platform_artifact_id=(
                    str(artifact_id)
                    if artifact_id is not None
                    else None
                ),
                platform_content_hash=(
                    content_hash
                ),
                uid=(
                    int(uid)
                    if isinstance(
                        uid,
                        int,
                    )
                    else None
                ),
                size_bytes=(
                    int(size_bytes)
                    if isinstance(
                        size_bytes,
                        int,
                    )
                    else path.stat().st_size
                ),
                submitted_at=(
                    str(submitted_at)
                    if submitted_at is not None
                    else None
                ),
            )

        finally:
            ledger.release_lock(
                artifact_hash
            )

    return {
        "status": "uploaded_unconfirmed",
        "acceptance": "unverified",
        "artifact_id": (
            str(artifact_id)
            if artifact_id is not None
            else None
        ),
        "content_hash": content_hash,
        "submitted_at": (
            str(submitted_at)
            if submitted_at is not None
            else None
        ),
        "uid": (
            uid
            if isinstance(uid, int)
            else None
        ),
        "size_bytes": (
            size_bytes
            if isinstance(
                size_bytes,
                int,
            )
            else path.stat().st_size
        ),
        "message": (
            "Artifact upload was acknowledged by Harnyx. "
            "Platform acceptance/batch membership has not yet "
            "been independently confirmed through Harnyx MCP."
        ),
    }