from __future__ import annotations

import httpx

from miner.services.mining_status import mining_status_snapshot


def _client(*, status: str, artifact_id: str = "artifact-1", response_status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if response_status != 200:
            return httpx.Response(response_status, json={"detail": "unavailable"})

        if request.url.path == "/v1/monitoring/miner-task-batches":
            return httpx.Response(
                200,
                json={
                    "batches": [
                        {
                            "batch_id": "batch-1",
                            "status": status,
                        }
                    ]
                },
            )

        if request.url.path == "/v1/monitoring/miner-task-batches/batch-1":
            return httpx.Response(
                200,
                json={
                    "batch": {
                        "artifacts": [
                            {
                                "artifact_id": artifact_id,
                                "content_hash": "artifact-hash",
                            }
                        ]
                    }
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
        },
    )


def test_running_batch_with_submitted_artifact_is_active() -> None:
    with _client(status="running") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "mining"
    assert snapshot["active"] is True
    assert snapshot["batch_status"] == "running"
    assert snapshot["batch_id"] == "batch-1"
    assert snapshot["artifact_id"] == "artifact-1"


def test_initializing_batch_is_not_reported_as_active_mining() -> None:
    with _client(status="initializing") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "initializing"
    assert snapshot["active"] is False


def test_running_batch_without_our_artifact_is_inactive() -> None:
    with _client(status="running", artifact_id="another-artifact") as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "inactive"
    assert snapshot["active"] is False


def test_monitoring_failure_fails_closed() -> None:
    with _client(status="running", response_status=503) as client:
        snapshot = mining_status_snapshot(client=client, uploads=_uploads())

    assert snapshot["status"] == "unknown"
    assert snapshot["active"] is False


def test_no_recorded_submission_is_inactive_without_remote_state() -> None:
    with _client(status="running") as client:
        snapshot = mining_status_snapshot(client=client, uploads=())

    assert snapshot["status"] == "inactive"
    assert snapshot["active"] is False
