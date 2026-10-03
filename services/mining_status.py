"""Normalized production-mining lifecycle state for the Miner UI."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..utils.config_loader import get_config_section
from ..utils.miner_errors import MinerError
from ..utils.miner_helpers import PROJECT_ROOT, require_external_repository, run_checked
from .artifact_submission import list_artifact_candidates

_TRACKED_BATCH_STATUSES = frozenset(("initializing", "running"))
_PROVIDER_CALLS = frozenset(("llm_chat", "search_web", "fetch_page", "embed_text"))
_SOURCE = "harnyx_public_monitoring"
_MCP_PROTOCOL_VERSION = "2025-06-18"
_MCP_CLIENT_INFO = {"name": "slai-harnyx-miner-dashboard", "version": "0.1.0"}


def mining_status_snapshot(
    *,
    client: httpx.Client | None = None,
    uploads: Sequence[Mapping[str, Any]] | None = None,
    miner_config: Mapping[str, Any] | None = None,
    mcp_tools: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a single frontend-safe lifecycle snapshot."""
    checked_at = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []

    try:
        recorded_uploads = tuple(uploads) if uploads is not None else _recorded_uploads()
    except Exception:
        recorded_uploads = ()
        errors.append("Local submission history could not be read.")

    netuid = _int_or_none(get_config_section("project").get("netuid"))

    config_payload = miner_config
    if config_payload is None:
        try:
            config_payload = _read_miner_config()
        except (MinerError, RuntimeError, OSError, ValueError):
            config_payload = None
            errors.append("Harnyx authenticated miner configuration is unavailable.")

    registration, harnyx_auth, providers = _identity_and_provider_state(
        config_payload,
        netuid=netuid,
    )

    owns_client = client is None
    if client is None:
        base_url = _platform_base_url()
        if base_url:
            try:
                client = httpx.Client(
                    base_url=base_url,
                    timeout=_request_timeout_seconds(),
                    follow_redirects=True,
                )
            except (OSError, TypeError, ValueError):
                client = None
                errors.append("Harnyx public monitoring client could not be initialized.")

    tool_payloads = dict(mcp_tools or {})
    if not tool_payloads:
        base_url = _platform_base_url()
        if base_url:
            try:
                tool_payloads = _public_mcp_snapshot(base_url)
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
                errors.append("Harnyx public monitoring MCP is unavailable.")

    candidate = _candidate_for_miner(
        _rows(tool_payloads.get("get_latest_submissions"), "rows"),
        hotkey_ss58=_text(harnyx_auth.get("hotkey_ss58")),
        uid=_int_or_none(harnyx_auth.get("uid")),
        uploads=recorded_uploads,
    )
    target = _target_identity(candidate, recorded_uploads, harnyx_auth)

    local_artifact = _local_artifact_for_hash(_text(target.get("content_hash")))
    providers = _complete_provider_state(
        providers,
        _artifact_required_providers(local_artifact),
    )

    remote: dict[str, Any] = {}
    remote_error = False
    if client is not None:
        try:
            remote = _remote_lifecycle(
                client,
                target=target,
                uploads=recorded_uploads,
            )
        except (httpx.HTTPError, ValueError, TypeError):
            remote_error = True
            errors.append("Harnyx batch monitoring is unavailable.")

    batch = _mapping(remote.get("batch"))
    matched_artifact = _mapping(remote.get("matched_artifact"))
    candidate_status = (
        "current_candidate"
        if candidate
        else "moved_to_batch"
        if batch
        else "unknown"
        if harnyx_auth.get("status") != "authenticated"
        else "not_current"
    )

    artifact = _artifact_state(
        target=target,
        candidate=candidate,
        batch=batch,
        matched_artifact=matched_artifact,
        local_artifact=local_artifact,
        recorded_uploads=recorded_uploads,
        candidate_status=candidate_status,
    )
    scheduler = _scheduler_state(_mapping(tool_payloads.get("get_validators")))
    validator_execution = _validator_execution_state(batch, matched_artifact)

    comparison: Mapping[str, Any] = {}
    batch_id = _text(batch.get("batch_id"))
    artifact_id = _text(artifact.get("artifact_id"))
    if batch_id and artifact_id and _text(batch.get("status")).lower() == "completed":
        injected = tool_payloads.get("get_miner_task_batch_artifact_comparison")
        if isinstance(injected, Mapping):
            comparison = injected
        else:
            base_url = _platform_base_url()
            if base_url:
                try:
                    comparison = _mcp_artifact_comparison(
                        base_url,
                        batch_id=batch_id,
                        artifact_id=artifact_id,
                    )
                except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
                    errors.append("Harnyx finalized artifact comparison is unavailable.")

    evaluation = _evaluation_state(batch, matched_artifact, comparison)
    allocation = _allocation_state(comparison)
    onchain = _onchain_state(netuid=netuid)
    phase = _phase(
        registration=registration,
        harnyx_auth=harnyx_auth,
        providers=providers,
        artifact=artifact,
        batch=batch,
        validator_execution=validator_execution,
        evaluation=evaluation,
        allocation=allocation,
        onchain=onchain,
    )

    coarse_status = "inactive"
    batch_status = _text(batch.get("status")).lower()
    if batch_status == "initializing":
        coarse_status = "initializing"
    elif batch_status == "running":
        coarse_status = "mining"
    elif remote_error and recorded_uploads:
        coarse_status = "unknown"
    elif not any((candidate, batch, recorded_uploads, config_payload)):
        coarse_status = "unknown" if errors else "inactive"

    response = {
        "status": coarse_status,
        "active": coarse_status == "mining",
        "batch_id": batch_id or None,
        "batch_status": _text(batch.get("status")) or None,
        "artifact_id": artifact_id or None,
        "source": _SOURCE,
        "checked_at": checked_at,
        "phase": phase,
        "summary": _summary_for_phase(phase, batch, artifact),
        "registration": registration,
        "harnyx_auth": harnyx_auth,
        "providers": providers,
        "artifact": artifact,
        "scheduler": scheduler,
        "batch": batch or None,
        "validator_execution": validator_execution,
        "evaluation": evaluation,
        "allocation": allocation,
        "onchain": onchain,
        "errors": errors,
    }
    if owns_client and client is not None:
        client.close()
    return response


def _remote_lifecycle(
    client: httpx.Client,
    *,
    target: Mapping[str, Any],
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

    batches = [
        item
        for item in _sequence(payload.get("batches"))
        if isinstance(item, Mapping)
    ]
    active = [
        item for item in batches
        if _text(item.get("status")).lower() in _TRACKED_BATCH_STATUSES
    ]
    completed = [
        item for item in batches
        if _text(item.get("status")).lower() in {"completed", "failed"}
    ]
    hotkey = _text(target.get("miner_hotkey_ss58"))
    uid = _int_or_none(target.get("uid"))

    for summary in active:
        match = _batch_match(
            client,
            summary,
            target=target,
            uploads=uploads,
            hotkey=hotkey,
            uid=uid,
            allow_identity_fallback=True,
        )
        if match:
            return match

    if _text(target.get("artifact_id")) or _text(target.get("content_hash")):
        for summary in completed[: _completed_scan_limit()]:
            match = _batch_match(
                client,
                summary,
                target=target,
                uploads=uploads,
                hotkey=hotkey,
                uid=uid,
                allow_identity_fallback=False,
            )
            if match:
                return match

    return {}


def _batch_match(
    client: httpx.Client,
    summary: Mapping[str, Any],
    *,
    target: Mapping[str, Any],
    uploads: Sequence[Mapping[str, Any]],
    hotkey: str,
    uid: int | None,
    allow_identity_fallback: bool,
) -> dict[str, Any] | None:
    batch_id = _text(summary.get("batch_id"))
    if not batch_id:
        return None

    response = client.get(f"/v1/monitoring/miner-task-batches/{batch_id}")
    response.raise_for_status()
    detail = response.json()
    if not isinstance(detail, Mapping):
        raise ValueError("Harnyx batch detail must be a JSON object.")

    matched = _matching_artifact(
        detail,
        target=target,
        uploads=uploads,
        hotkey=hotkey,
        uid=uid,
        allow_identity_fallback=allow_identity_fallback,
    )
    if matched is None:
        return None

    normalized = dict(summary)
    for key, value in _mapping(detail.get("summary")).items():
        if value is not None:
            normalized[key] = value
    normalized["detail_source"] = _SOURCE
    return {"batch": normalized, "matched_artifact": dict(matched)}


def _matching_artifact(
    detail: Mapping[str, Any],
    *,
    target: Mapping[str, Any],
    uploads: Sequence[Mapping[str, Any]],
    hotkey: str,
    uid: int | None,
    allow_identity_fallback: bool,
) -> Mapping[str, Any] | None:
    artifacts = _artifact_rows(detail)
    if not artifacts:
        return None

    target_artifact_id = _text(target.get("artifact_id"))
    target_content_hash = _text(target.get("content_hash")).lower()
    artifact_ids = {target_artifact_id} if target_artifact_id else set()
    hashes = {target_content_hash} if target_content_hash else set()

    # Never associate a current candidate with an older artifact from the same
    # hotkey. Historical uploads are only a fallback when no current artifact
    # identity is available at all.
    if not artifact_ids and not hashes:
        artifact_ids = {
            value
            for value in (
                _text(item.get("platform_artifact_id")) for item in uploads
            )
            if value
        }
        hashes = {
            value.lower()
            for value in (
                _text(item.get("platform_content_hash")) for item in uploads
            )
            if value
        }

    for artifact in artifacts:
        artifact_id = _text(artifact.get("artifact_id"))
        content_hash = _text(artifact.get("content_hash")).lower()
        if artifact_id and artifact_id in artifact_ids:
            return artifact
        if content_hash and content_hash in hashes:
            return artifact

    if artifact_ids or hashes or not allow_identity_fallback:
        return None

    if hotkey:
        for artifact in artifacts:
            if _text(artifact.get("miner_hotkey_ss58")) == hotkey:
                return artifact
    if uid is not None:
        for artifact in artifacts:
            if _int_or_none(artifact.get("uid")) == uid:
                return artifact
    return None


def _artifact_rows(detail: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    batch = _mapping(detail.get("batch"))
    for value in (batch.get("artifacts"), detail.get("artifacts")):
        rows = _sequence(value)
        if rows:
            return tuple(item for item in rows if isinstance(item, Mapping))
    return ()


def _identity_and_provider_state(
    config: Mapping[str, Any] | None,
    *,
    netuid: int | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if config is None:
        return (
            {"status": "unknown", "netuid": netuid, "uid": None, "hotkey_ss58": None, "network": None, "source": "harnyx_miner_config"},
            {"status": "unknown", "uid": None, "hotkey_ss58": None, "message": "Authenticated Harnyx miner configuration is unavailable."},
            {"status": "unknown", "required": [], "configured": [], "missing": [], "requirements_complete": False},
        )

    uid = _int_or_none(config.get("uid"))
    hotkey = _text(config.get("miner_hotkey_ss58")) or None
    authenticated = uid is not None and hotkey is not None
    configured = sorted(
        str(provider)
        for provider, raw in _mapping(config.get("provider_credentials")).items()
        if _mapping(raw).get("exists") is True
    )
    return (
        {"status": "registered" if authenticated else "unknown", "netuid": netuid, "uid": uid, "hotkey_ss58": hotkey, "network": None, "source": "harnyx_miner_config"},
        {"status": "authenticated" if authenticated else "unknown", "uid": uid, "hotkey_ss58": hotkey, "message": None if authenticated else "Harnyx did not return a recognized UID/hotkey."},
        {"status": "unknown", "required": [], "configured": configured, "missing": [], "requirements_complete": False},
    )


def _complete_provider_state(current: Mapping[str, Any], requirement: Mapping[str, Any]) -> dict[str, Any]:
    configured = sorted(str(item) for item in _sequence(current.get("configured")))
    required = sorted(str(item) for item in _sequence(requirement.get("providers")))
    complete = requirement.get("complete") is True
    missing = sorted(set(required) - set(configured))
    status = "not_ready" if missing else "ready" if required and complete else "partial" if required else "unknown"
    return {"status": status, "required": required, "configured": configured, "missing": missing, "requirements_complete": complete}


def _artifact_required_providers(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"providers": [], "complete": False}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return {"providers": [], "complete": False}

    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = _literal_string(node.value, constants)
            if value:
                constants[node.targets[0].id] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = _literal_string(node.value, constants) if node.value is not None else None
            if value:
                constants[node.target.id] = value

    providers: set[str] = set()
    complete = True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) not in _PROVIDER_CALLS:
            continue
        keyword = next((item for item in node.keywords if item.arg == "provider"), None)
        if keyword is None:
            complete = False
            continue
        provider = _literal_string(keyword.value, constants)
        if provider:
            providers.add(provider)
        else:
            complete = False
    return {"providers": sorted(providers), "complete": complete and bool(providers)}


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_string(node: ast.expr | None, constants: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _local_artifact_for_hash(content_hash: str) -> Path | None:
    normalized = content_hash.lower()
    if len(normalized) != 64:
        return None
    root = (PROJECT_ROOT / "artifacts" / "harnyx").resolve()
    if not root.is_dir():
        return None
    for path in root.glob("*_agent.py"):
        if not path.is_file():
            continue
        try:
            if _sha256(path) == normalized:
                return path.resolve()
        except OSError:
            continue
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_state(*, target: Mapping[str, Any], candidate: Mapping[str, Any] | None, batch: Mapping[str, Any], matched_artifact: Mapping[str, Any], local_artifact: Path | None, recorded_uploads: Sequence[Mapping[str, Any]], candidate_status: str) -> dict[str, Any]:
    upload = _latest_upload(recorded_uploads)
    source = candidate or matched_artifact or target or upload
    artifact_id = _text(source.get("artifact_id")) or _text(source.get("platform_artifact_id")) or _text(target.get("artifact_id")) or None
    content_hash = _text(source.get("content_hash")) or _text(source.get("platform_content_hash")) or _text(target.get("content_hash")) or None
    submitted_at = _text(source.get("submitted_at")) or _text(upload.get("submitted_at")) or None
    uid = _int_or_none(source.get("uid"))
    if uid is None:
        uid = _int_or_none(target.get("uid"))
    size_bytes = _int_or_none(source.get("size_bytes"))
    if size_bytes is None and local_artifact is not None:
        try:
            size_bytes = local_artifact.stat().st_size
        except OSError:
            pass
    accepted = bool(artifact_id or candidate or batch or upload)
    return {"status": "accepted" if accepted else "unknown", "acceptance": "accepted" if accepted else "unverified", "artifact_id": artifact_id, "content_hash": content_hash, "submitted_at": submitted_at, "uid": uid, "filename": local_artifact.name if local_artifact is not None else None, "size_bytes": size_bytes, "candidate_status": candidate_status}


def _candidate_for_miner(rows: Sequence[Mapping[str, Any]], *, hotkey_ss58: str, uid: int | None, uploads: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if hotkey_ss58:
        for row in rows:
            if _text(row.get("miner_hotkey_ss58")) == hotkey_ss58:
                return row
    if uid is not None:
        for row in rows:
            if _int_or_none(row.get("uid")) == uid:
                return row
    artifact_ids = {_text(item.get("platform_artifact_id")) for item in uploads if _text(item.get("platform_artifact_id"))}
    hashes = {_text(item.get("platform_content_hash")).lower() for item in uploads if _text(item.get("platform_content_hash"))}
    for row in rows:
        if _text(row.get("artifact_id")) in artifact_ids or _text(row.get("content_hash")).lower() in hashes:
            return row
    return None


def _target_identity(candidate: Mapping[str, Any] | None, uploads: Sequence[Mapping[str, Any]], auth: Mapping[str, Any]) -> dict[str, Any]:
    upload = _latest_upload(uploads)
    source = candidate or upload
    uid = _int_or_none(source.get("uid"))
    return {"artifact_id": _text(source.get("artifact_id")) or _text(source.get("platform_artifact_id")), "content_hash": _text(source.get("content_hash")) or _text(source.get("platform_content_hash")), "uid": uid if uid is not None else _int_or_none(auth.get("uid")), "miner_hotkey_ss58": _text(source.get("miner_hotkey_ss58")) or _text(auth.get("hotkey_ss58")), "submitted_at": _text(source.get("submitted_at")), "size_bytes": _int_or_none(source.get("size_bytes"))}


def _latest_upload(uploads: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    return max(uploads, key=lambda item: _text(item.get("submitted_at"))) if uploads else {}


def _scheduler_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _mapping(payload.get("runtime"))
    health = _mapping(payload.get("validator_health"))
    next_batch = runtime.get("next_scheduled_batch_at")
    status = "unknown" if "next_scheduled_batch_at" not in runtime else "disabled" if next_batch in (None, "") else "scheduled"
    return {"status": status, "next_scheduled_batch_at": _text(next_batch) or None, "cron": _text(runtime.get("miner_task_schedule_cron")) or None, "evaluation_timeout_seconds": _number_or_none(runtime.get("miner_evaluation_timeout_seconds")), "validator_health": {"healthy": _int_or_none(health.get("healthy")), "unhealthy": _int_or_none(health.get("unhealthy")), "unknown": _int_or_none(health.get("unknown"))}}


def _validator_execution_state(batch: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    if not batch:
        return {"status": "not_started", "validator_count": None, "resolved_count": None, "total_count": None, "percent_complete": None, "started_at": None, "stage": None}
    progress = _mapping(batch.get("stage_progress"))
    validators = [item for item in _sequence(progress.get("validators")) if isinstance(item, Mapping)]
    stage = _text(progress.get("stage"))
    artifact_status = (_text(artifact.get("delivery_status")) or _text(artifact.get("execution_status")) or _text(artifact.get("status"))).lower()
    if artifact_status in {"running", "executing", "in_progress", "delivered"}:
        status = "running"
    elif artifact_status == "completed":
        status = "completed"
    elif _text(batch.get("status")).lower() == "running" and stage == "running_and_scoring_tasks":
        status = "batch_running_unconfirmed"
    elif _text(batch.get("status")).lower() == "initializing":
        status = "not_started"
    elif _text(batch.get("status")).lower() in {"completed", "failed"}:
        status = "complete_or_unavailable"
    else:
        status = "unknown"
    resolved = sum(_int_or_none(item.get("resolved_count")) or 0 for item in validators)
    total = sum(_int_or_none(item.get("total_count")) or 0 for item in validators)
    return {"status": status, "validator_count": len(validators) if validators else None, "resolved_count": resolved if validators else None, "total_count": total if validators else None, "percent_complete": (resolved / total * 100.0) if total else None, "started_at": _text(progress.get("started_at")) or None, "stage": stage or None}


def _evaluation_state(batch: Mapping[str, Any], artifact: Mapping[str, Any], comparison: Mapping[str, Any]) -> dict[str, Any]:
    batch_status = _text(batch.get("status")).lower()
    stage = _text(batch.get("evaluation_stage")).lower()
    explicit_main = _bool_first(artifact.get("main_admitted"), artifact.get("admitted_to_main"), comparison.get("main_admitted"), comparison.get("admitted_to_main"))
    qualifying = "running" if stage == "qualifying" and batch_status == "running" else "pending" if stage == "qualifying" and batch_status == "initializing" else "complete" if explicit_main is True or stage == "main" or (batch_status == "completed" and stage == "qualifying") else "unknown"
    main = "running" if explicit_main is True and batch_status == "running" else "complete" if explicit_main is True and batch_status == "completed" else "admitted" if explicit_main is True else "not_admitted" if explicit_main is False else "unknown" if stage == "main" and batch_status in {"running", "completed"} else "not_started"
    total_score = _number_first(comparison.get("total_score"), artifact.get("total_score"), comparison.get("score"))
    error_counts = comparison.get("error_counts")
    if not isinstance(error_counts, Mapping):
        error_counts = artifact.get("error_counts")
    return {"qualifying_status": qualifying, "main_status": main, "main_admitted": explicit_main, "final_status": "scored" if batch_status == "completed" and total_score is not None else "complete_score_unavailable" if batch_status == "completed" else "pending", "qualifying_score": _number_first(comparison.get("qualifying_score"), artifact.get("qualifying_score")), "total_score": total_score, "comparison_score": _number_first(comparison.get("comparison_score"), artifact.get("comparison_score")), "median_cost_usd": _number_first(comparison.get("median_cost_usd"), artifact.get("median_cost_usd"), comparison.get("cost_usd")), "total_cost_usd": _number_first(comparison.get("total_cost_usd"), artifact.get("total_cost_usd")), "median_runtime_ms": _number_first(comparison.get("median_elapsed_ms"), comparison.get("median_runtime_ms"), artifact.get("median_elapsed_ms"), artifact.get("median_runtime_ms")), "novelty_classification": _text(comparison.get("novelty_classification")) or _text(comparison.get("novelty")) or _text(artifact.get("novelty_classification")) or None, "error_counts": dict(error_counts) if isinstance(error_counts, Mapping) else None, "source": "harnyx_official_results" if comparison else "harnyx_batch_monitoring"}


def _allocation_state(comparison: Mapping[str, Any]) -> dict[str, Any]:
    reward_eligible = _bool_first(comparison.get("reward_eligible"), comparison.get("participant_reward_eligible"))
    weight = _number_first(comparison.get("weight"), comparison.get("allocation"), comparison.get("participant_weight"), comparison.get("reward_weight"))
    status = "calculated" if weight is not None else "no_participant_allocation" if reward_eligible is False else "eligible_pending_weight" if reward_eligible is True else "unknown"
    return {"status": status, "reward_eligible": reward_eligible, "weight": weight, "source_batch_id": _text(comparison.get("batch_id")) or None, "source": "harnyx_artifact_comparison" if comparison else None}


def _onchain_state(*, netuid: int | None) -> dict[str, Any]:
    return {"status": "unavailable", "netuid": netuid, "weight_submitted": None, "incentive": None, "emission_tao": None, "rank": None, "trust": None, "consensus": None, "stake": None, "last_update": None, "source": "bittensor", "message": "This repository has no authoritative read-only metagraph/weight-submission integration yet. Wallet balance and cumulative earnings are not treated as proof of current SN67 emission."}


def _phase(*, registration: Mapping[str, Any], harnyx_auth: Mapping[str, Any], providers: Mapping[str, Any], artifact: Mapping[str, Any], batch: Mapping[str, Any], validator_execution: Mapping[str, Any], evaluation: Mapping[str, Any], allocation: Mapping[str, Any], onchain: Mapping[str, Any]) -> str:
    if onchain.get("status") == "emitting": return "emitting"
    if onchain.get("weight_submitted") is True: return "onchain"
    if allocation.get("status") == "calculated": return "weight_calculated"
    if evaluation.get("final_status") in {"scored", "complete_score_unavailable"}: return "scored"
    if evaluation.get("main_status") in {"running", "admitted"}: return "main"
    if _text(batch.get("evaluation_stage")).lower() == "qualifying" and _text(batch.get("status")).lower() == "running": return "qualifying"
    if validator_execution.get("status") == "running": return "validator_running"
    if batch: return "batch_selected"
    if artifact.get("candidate_status") == "current_candidate": return "candidate"
    if artifact.get("acceptance") == "accepted": return "submitted"
    if providers.get("status") == "not_ready": return "provider_not_ready"
    if harnyx_auth.get("status") == "authenticated": return "authenticated"
    if registration.get("status") == "registered": return "registered"
    return "unknown"


def _summary_for_phase(phase: str, batch: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    labels = {"registered": ("REGISTERED", "SN67 registration is recognized."), "authenticated": ("HARNYX CONNECTED", "Harnyx recognizes the signing hotkey."), "provider_not_ready": ("PROVIDER ACTION REQUIRED", "At least one known required provider is not configured."), "submitted": ("SUBMITTED", "Artifact upload is accepted; candidate state is not confirmed."), "candidate": ("READY — AWAITING BATCH SELECTION", "The artifact is Harnyx's current candidate for this miner."), "batch_selected": ("BATCH SELECTED", "The artifact is present in finalized batch membership."), "validator_running": ("ACTIVE — VALIDATORS EXECUTING", "Artifact-level validator execution is confirmed."), "qualifying": ("ACTIVE — QUALIFYING", "The selected artifact is in the qualifying evaluation stage."), "main": ("ACTIVE — MAIN EVALUATION", "The artifact is in the main evaluation stage."), "scored": ("EVALUATION COMPLETE", "Harnyx finalized this batch; official result fields are shown when exposed."), "weight_calculated": ("ALLOCATION CALCULATED", "Harnyx exposed an allocation/weight value for the artifact."), "onchain": ("WEIGHT SUBMITTED ON-CHAIN", "Bittensor weight submission is independently confirmed."), "emitting": ("EMISSION ACTIVE", "Current on-chain emission is independently confirmed."), "unknown": ("STATUS UNKNOWN", "Reliable production lifecycle data is currently unavailable.")}
    title, detail = labels.get(phase, (phase.replace("_", " ").upper(), ""))
    next_step = {"candidate": "Batch selection", "batch_selected": "Validator execution", "qualifying": "Qualifying completion / main admission", "main": "Final scoring", "scored": "Allocation / weight calculation", "weight_calculated": "Bittensor on-chain confirmation"}.get(phase)
    return {"title": title, "detail": detail, "next_step": next_step, "batch_id": _text(batch.get("batch_id")) or None, "artifact_id": _text(artifact.get("artifact_id")) or None}


def _read_miner_config() -> Mapping[str, Any] | None:
    submission = get_config_section("submission")
    base_url = os.getenv(str(submission.get("platform_base_url_env") or "PLATFORM_BASE_URL"), "").strip()
    wallet_name = os.getenv(str(submission.get("wallet_name_env") or "HARNYX_WALLET_NAME"), "").strip()
    hotkey_name = os.getenv(str(submission.get("hotkey_name_env") or "HARNYX_HOTKEY_NAME"), "").strip()
    if not base_url or not wallet_name or not hotkey_name: return None
    harnyx = require_external_repository("harnyx", "miner/src/harnyx_miner/miner_config.py")
    completed = run_checked(["uv", "run", "--frozen", "--package", "harnyx-miner", "harnyx-miner-config", "--wallet-name", wallet_name, "--hotkey-name", hotkey_name, "--get"], cwd=harnyx, timeout=30, env_overrides={"PLATFORM_BASE_URL": base_url})
    raw = _json_result(completed.stdout)
    return {"miner_hotkey_ss58": raw.get("miner_hotkey_ss58"), "uid": raw.get("uid"), "task_retry_count": raw.get("task_retry_count"), "provider_credentials": _sanitized_provider_credentials(raw.get("provider_credentials"))}


def _sanitized_provider_credentials(value: object) -> dict[str, Any]:
    return {str(provider): {"provider": str(provider), "exists": _mapping(raw).get("exists") is True, "created_at": _mapping(raw).get("created_at"), "updated_at": _mapping(raw).get("updated_at")} for provider, raw in _mapping(value).items()}


def _json_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line: continue
        try: value = json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(value, dict): return value
    raise RuntimeError("Harnyx command returned no machine-readable JSON object.")


def _public_mcp_snapshot(base_url: str) -> dict[str, Mapping[str, Any]]:
    return _mcp_tools(base_url, {"get_latest_submissions": {}, "get_validators": {}})


def _mcp_artifact_comparison(base_url: str, *, batch_id: str, artifact_id: str) -> Mapping[str, Any]:
    return _mcp_tools(base_url, {"get_miner_task_batch_artifact_comparison": {"batch_id": batch_id, "artifact_id": artifact_id}}).get("get_miner_task_batch_artifact_comparison", {})


def _mcp_tools(base_url: str, calls: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    endpoint = f"{base_url.rstrip('/')}/mcp"
    output: dict[str, Mapping[str, Any]] = {}
    with httpx.Client(timeout=_mcp_timeout_seconds(), follow_redirects=True) as client:
        init, response = _mcp_request_with_response(client, endpoint, headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}, payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": _MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": _MCP_CLIENT_INFO}})
        protocol = _text(_mapping(init.get("result")).get("protocolVersion")) or _MCP_PROTOCOL_VERSION
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": protocol}
        session_id = response.headers.get("mcp-session-id")
        if session_id: headers["Mcp-Session-Id"] = session_id
        initialized = client.post(endpoint, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        if initialized.status_code not in {200, 202, 204}: initialized.raise_for_status()
        for request_id, (name, arguments) in enumerate(calls.items(), start=10):
            message, _ = _mcp_request_with_response(client, endpoint, headers=headers, payload={"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": dict(arguments)}})
            error = message.get("error")
            if isinstance(error, Mapping): raise RuntimeError(str(error.get("message") or "MCP request failed."))
            output[name] = _mcp_tool_payload(_mapping(message.get("result")))
        if session_id:
            try: client.delete(endpoint, headers=headers)
            except httpx.HTTPError: pass
    return output


def _mcp_request_with_response(client: httpx.Client, endpoint: str, *, headers: Mapping[str, str], payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], httpx.Response]:
    response = client.post(endpoint, headers=dict(headers), json=dict(payload)); response.raise_for_status(); return _mcp_message(response), response


def _mcp_message(response: httpx.Response) -> Mapping[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = response.json()
        if isinstance(payload, Mapping): return payload
        raise ValueError("MCP JSON response must be an object.")
    if "text/event-stream" in content_type:
        messages: list[Mapping[str, Any]] = []
        for line in response.text.splitlines():
            if not line.strip().startswith("data:"): continue
            try: value = json.loads(line.strip()[5:].strip())
            except json.JSONDecodeError: continue
            if isinstance(value, Mapping): messages.append(value)
        if messages: return messages[-1]
        raise ValueError("MCP SSE response contained no JSON-RPC message.")
    payload = response.json()
    if isinstance(payload, Mapping): return payload
    raise ValueError("MCP response must be a JSON object.")


def _mcp_tool_payload(result: Mapping[str, Any]) -> Mapping[str, Any]:
    structured = result.get("structuredContent")
    if not isinstance(structured, Mapping): structured = result.get("structured_content")
    if isinstance(structured, Mapping): return dict(structured)
    for item in _sequence(result.get("content")):
        if not isinstance(item, Mapping) or item.get("type") != "text": continue
        try: payload = json.loads(_text(item.get("text")))
        except json.JSONDecodeError: continue
        if isinstance(payload, Mapping): return dict(payload)
    return {}


def _recorded_uploads() -> tuple[Mapping[str, Any], ...]:
    uploads: list[Mapping[str, Any]] = []; seen: set[tuple[str, str]] = set()
    for candidate in list_artifact_candidates():
        previous = candidate.get("previous_upload")
        if not isinstance(previous, Mapping): continue
        artifact_id = _text(previous.get("platform_artifact_id")); content_hash = _text(previous.get("platform_content_hash")).lower()
        if not artifact_id and not content_hash: continue
        key = (artifact_id, content_hash)
        if key not in seen: seen.add(key); uploads.append(previous)
    return tuple(uploads)


def _platform_base_url() -> str | None:
    config = get_config_section("submission"); env_name = str(config.get("platform_base_url_env") or "PLATFORM_BASE_URL"); value = os.getenv(env_name, "").strip(); return value.rstrip("/") if value else None


def _numeric_config(key: str, default: float) -> float:
    raw = get_config_section("submission").get(key, default); return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else default


def _request_timeout_seconds() -> float: return _numeric_config("monitoring_timeout_seconds", 8.0)
def _mcp_timeout_seconds() -> float: return _numeric_config("monitoring_mcp_timeout_seconds", 12.0)
def _batch_limit() -> int:
    raw = get_config_section("submission").get("monitoring_batch_limit", 25); return raw if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 100 else 25

def _completed_scan_limit() -> int:
    raw = get_config_section("submission").get("monitoring_completed_scan_limit", 4); return raw if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 20 else 4

def _rows(payload: Mapping[str, Any] | None, key: str) -> tuple[Mapping[str, Any], ...]: return tuple(item for item in _sequence(_mapping(payload).get(key)) if isinstance(item, Mapping))
def _mapping(value: object) -> Mapping[str, Any]: return value if isinstance(value, Mapping) else {}
def _sequence(value: object) -> Sequence[Any]: return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()
def _text(value: object) -> str: return value.strip() if isinstance(value, str) else ""
def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool): return None
    if isinstance(value, int): return value
    if isinstance(value, float) and value.is_integer(): return int(value)
    return None

def _number_or_none(value: object) -> float | None: return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
def _number_first(*values: object) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None: return number
    return None

def _bool_first(*values: object) -> bool | None: return next((value for value in values if isinstance(value, bool)), None)


__all__ = ["mining_status_snapshot"]
