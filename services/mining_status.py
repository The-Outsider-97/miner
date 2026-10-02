"""Read-only Harnyx batch monitoring for the Miner UI."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import httpx

from ..utils.config_loader import get_config_section
from .artifact_submission import list_artifact_candidates

_ACTIVE_BATCH_STATUS = "running"
_TRACKED_BATCH_STATUSES = frozenset(("initializing", "running"))
_SOURCE = "harnyx_public_monitoring"


def mining_status_snapshot(
    *,
    client: httpx.Client | None = None,
    uploads: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return fail-closed mining state from Harnyx public batch monitoring."""
    recorded_uploads = tuple(uploads) if uploads is not None else _recorded_uploads()
    if not recorded_uploads:
        return _snapshot("inactive")

    owns_client = client is None
    if client is None:
        base_url = _platform_base_url()
        if base_url is None:
            return _snapshot("unknown")
        client = httpx.Client(
            base_url=base_url,
            timeout=_request_timeout_seconds(),
            follow_redirects=True,
        )

    try:
        return _remote_snapshot(client, recorded_uploads)
    except (httpx.HTTPError, ValueError, TypeError):
        return _snapshot("unknown")
    finally:
        if owns_client:
            client.close()


def _remote_snapshot(
    client: httpx.Client,
    uploads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    response = client.get(
        "/v1/monitoring/miner-task-batches",
        params={"limit": _batch_limit()},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Harnyx monitoring response must be a JSON object.")

    raw_batches = payload.get("batches")
    if not isinstance(raw_batches, Sequence) or isinstance(raw_batches, (str, bytes, bytearray)):
        raise ValueError("Harnyx monitoring response does not contain a batch list.")

    initializing_match: dict[str, Any] | None = None

    for raw_batch in raw_batches:
        if not isinstance(raw_batch, Mapping):
            continue
        batch_status = _text(raw_batch.get("status")).lower()
        if batch_status not in _TRACKED_BATCH_STATUSES:
            continue
        batch_id = _text(raw_batch.get("batch_id"))
        if not batch_id:
            continue

        detail_response = client.get(f"/v1/monitoring/miner-task-batches/{batch_id}")
        detail_response.raise_for_status()
        detail = detail_response.json()
        if not isinstance(detail, Mapping):
            raise ValueError("Harnyx batch detail must be a JSON object.")

        matched = _matching_artifact(detail, uploads)
        if matched is None:
            continue

        if batch_status == _ACTIVE_BATCH_STATUS:
            return _snapshot(
                "mining",
                active=True,
                batch_id=batch_id,
                batch_status=batch_status,
                artifact_id=_text(matched.get("artifact_id")) or None,
            )

        initializing_match = _snapshot(
            "initializing",
            batch_id=batch_id,
            batch_status=batch_status,
            artifact_id=_text(matched.get("artifact_id")) or None,
        )

    return initializing_match or _snapshot("inactive")


def _matching_artifact(
    detail: Mapping[str, Any],
    uploads: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    batch = detail.get("batch")
    if not isinstance(batch, Mapping):
        return None
    raw_artifacts = batch.get("artifacts")
    if not isinstance(raw_artifacts, Sequence) or isinstance(raw_artifacts, (str, bytes, bytearray)):
        return None

    artifact_ids = {
        _text(upload.get("platform_artifact_id"))
        for upload in uploads
        if _text(upload.get("platform_artifact_id"))
    }
    content_hashes = {
        _text(upload.get("platform_content_hash")).lower()
        for upload in uploads
        if _text(upload.get("platform_content_hash"))
    }

    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, Mapping):
            continue
        artifact_id = _text(raw_artifact.get("artifact_id"))
        content_hash = _text(raw_artifact.get("content_hash")).lower()
        if (artifact_id and artifact_id in artifact_ids) or (
            content_hash and content_hash in content_hashes
        ):
            return raw_artifact
    return None


def _recorded_uploads() -> tuple[Mapping[str, Any], ...]:
    uploads: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in list_artifact_candidates():
        previous = candidate.get("previous_upload")
        if not isinstance(previous, Mapping):
            continue
        artifact_id = _text(previous.get("platform_artifact_id"))
        content_hash = _text(previous.get("platform_content_hash")).lower()
        if not artifact_id and not content_hash:
            continue
        key = (artifact_id, content_hash)
        if key in seen:
            continue
        seen.add(key)
        uploads.append(previous)
    return tuple(uploads)


def _platform_base_url() -> str | None:
    config = get_config_section("submission")
    env_name = str(config.get("platform_base_url_env") or "PLATFORM_BASE_URL")
    value = os.getenv(env_name, "").strip()
    return value.rstrip("/") if value else None


def _request_timeout_seconds() -> float:
    config = get_config_section("submission")
    raw = config.get("monitoring_timeout_seconds", 5.0)
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 5.0


def _batch_limit() -> int:
    config = get_config_section("submission")
    raw = config.get("monitoring_batch_limit", 25)
    if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 100:
        return raw
    return 25


def _snapshot(
    status: str,
    *,
    active: bool = False,
    batch_id: str | None = None,
    batch_status: str | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "active": bool(active and batch_status == _ACTIVE_BATCH_STATUS),
        "batch_id": batch_id,
        "batch_status": batch_status,
        "artifact_id": artifact_id,
        "source": _SOURCE,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["mining_status_snapshot"]
