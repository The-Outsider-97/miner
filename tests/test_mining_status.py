from __future__ import annotations

import httpx

from miner.services.mining_status import mining_status_snapshot


def _client(
    *,
    status: str | None,
    artifact_id: str = "artifact-1",
    response_status: int = 200,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if response_status != 200:
            return httpx.Response(response_status, json={"detail": "unavailable"})

        if request.url.path == "/v1/monitoring/miner-task-batches":
            batches = [] if status is None else [
                {
                    "batch_id": "batch-1",
                    "status": status,
                    "evaluation_stage": "qualifying",
                    "cutoff_at": "2026-10-03T15:00:00Z",
                    "qualifying_task_count": 10,
                    "main_task_count": 0,
                }
            ]
            return httpx.Response(200, json={"batches": batches})

        if request.url.path == "/v1/monitoring/miner-task-batches/batch-1":
            return httpx.Response(
                200,
                json={
                    "summary": {
                        "batch_id": "batch-1",
                        "status": status,
                        "evaluation_stage": "qualifying",
                    },
                    "batch": {
                        "artifacts": [
                            {
                                "artifact_id": artifact_id,
                                "content_hash": "artifact-hash",
                            }
                        ]
                    },
                },
            )

        return httpx.Response(404, json={"detail": "not found"})

    return httpx.Client(
        base_url="https://platform.example.com",
        transport=httpx.MockTransport(handler),
    )


def _uploads() -> tuple[dict[str, object], ...]:
    return (
        {
            "platform_artifact_id": "artifact-1",
            "platform_content_hash": "artifact-hash",
            "submitted_at": "2026-10-02T20:37:06Z",
        },
    )


def _miner_config() -> dict[str, object]:
    return {
        "miner_hotkey_ss58": "5ExampleHotkey",
        "uid": 200,
        "provider_credentials": {
            "chutes": {
                "provider": "chutes",
                "exists": True,
                "api_key": "must-never-be-returned",
            }
        },
    }


def _mcp_tools() -> dict[str, dict[str, object]]:
    return {
        "get_latest_submissions": {
            "rows": [
                {
                    "uid": 200,
                    "artifact_id": "artifact-1",
                    "miner_hotkey_ss58": "5ExampleHotkey",
                    "content_hash": "artifact-hash",
                    "submitted_at": "2026-10-02T20:37:06Z",
                }
            ]
        },
        "get_validators": {
            "validator_health": {"healthy": 5, "unhealthy": 3, "unknown": 1},
            "runtime": {
                "miner_task_schedule_cron": "0 15 * * *",
                "next_scheduled_batch_at": "2026-10-03T15:00:00Z",
                "miner_evaluation_timeout_seconds": 129600.0,
            },
        },
    }


def test_running_batch_with_submitted_artifact_is_active() -> None:
    with _client(status="running") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "mining"
    assert snapshot["active"] is True
    assert snapshot["batch_status"] == "running"
    assert snapshot["batch_id"] == "batch-1"
    assert snapshot["artifact_id"] == "artifact-1"
    assert snapshot["phase"] == "qualifying"


def test_initializing_batch_is_not_reported_as_active_mining() -> None:
    with _client(status="initializing") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "initializing"
    assert snapshot["active"] is False
    assert snapshot["phase"] == "batch_selected"


def test_running_batch_without_our_artifact_is_inactive() -> None:
    with _client(status="running", artifact_id="another-artifact") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "inactive"
    assert snapshot["active"] is False
    assert snapshot["batch"] is None


def test_monitoring_failure_fails_closed() -> None:
    with _client(status="running", response_status=503) as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "unknown"
    assert snapshot["active"] is False
    assert snapshot["errors"]


def test_no_recorded_submission_is_inactive_without_remote_state() -> None:
    with _client(status=None) as client:
        snapshot = mining_status_snapshot(client=client, uploads=())

    assert snapshot["status"] == "inactive"
    assert snapshot["active"] is False


def test_current_submission_is_distinct_from_batch_selection() -> None:
    with _client(status=None) as client:
        snapshot = mining_status_snapshot(
            client=client,
            uploads=_uploads(),
            miner_config=_miner_config(),
            mcp_tools=_mcp_tools(),
        )

    assert snapshot["phase"] == "candidate"
    assert snapshot["artifact"]["candidate_status"] == "current_candidate"
    assert snapshot["batch"] is None
    assert snapshot["validator_execution"]["status"] == "not_started"


def test_scheduler_and_validator_health_are_normalized() -> None:
    with _client(status=None) as client:
        snapshot = mining_status_snapshot(
            client=client,
            uploads=_uploads(),
            miner_config=_miner_config(),
            mcp_tools=_mcp_tools(),
        )

    assert snapshot["scheduler"]["status"] == "scheduled"
    assert snapshot["scheduler"]["next_scheduled_batch_at"] == "2026-10-03T15:00:00Z"
    assert snapshot["scheduler"]["validator_health"] == {
        "healthy": 5,
        "unhealthy": 3,
        "unknown": 1,
    }


def test_provider_secrets_are_not_exposed() -> None:
    with _client(status=None) as client:
        snapshot = mining_status_snapshot(
            client=client,
            uploads=_uploads(),
            miner_config=_miner_config(),
            mcp_tools=_mcp_tools(),
        )

    assert snapshot["providers"]["configured"] == ["chutes"]
    assert "must-never-be-returned" not in repr(snapshot)


def test_onchain_state_stays_unavailable_without_authoritative_metagraph_data() -> None:
    with _client(status=None) as client:
        snapshot = mining_status_snapshot(
            client=client,
            uploads=_uploads(),
            miner_config=_miner_config(),
            mcp_tools=_mcp_tools(),
        )

    assert snapshot["onchain"]["status"] == "unavailable"
    assert snapshot["onchain"]["weight_submitted"] is None
    assert snapshot["onchain"]["emission_tao"] is None
