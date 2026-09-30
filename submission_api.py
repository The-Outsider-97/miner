"""Machine-readable server API for artifact discovery and submission."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from typing import Any

from .services.artifact_submission import (
    list_artifact_candidates,
    preflight_artifact,
    submit_artifact,
)
from .utils.miner_errors import (
    SubmissionConflictError,
    SubmissionError,
    SubmissionPreflightError,
    SubmissionRejectedError,
)


def _body() -> dict[str, Any]:
    raw = sys.stdin.read()

    if not raw.strip():
        return {}

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SubmissionPreflightError("Request body is not valid JSON.") from exc

    if not isinstance(value, Mapping):
        raise SubmissionPreflightError("Request body must be a JSON object.")

    return dict(value)


def _emit(payload: dict[str, Any]) -> int:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Miner artifact submission API.")
    parser.add_argument(
        "operation",
        choices=[
            "list",
            "preflight",
            "submit",
        ],
    )

    args = parser.parse_args(argv)

    try:
        if args.operation == "list":
            return _emit(
                {
                    "ok": True,
                    "artifacts": (
                        list_artifact_candidates()
                    ),
                }
            )

        body = _body()

        artifact_hash = body.get(
            "artifact_sha256"
        )

        if not isinstance(
            artifact_hash,
            str,
        ):
            raise SubmissionPreflightError(
                "artifact_sha256 is required."
            )

        if args.operation == "preflight":
            return _emit(
                {
                    "ok": True,
                    "preflight": (
                        preflight_artifact(
                            artifact_hash
                        )
                    ),
                }
            )

        if body.get("confirm") is not True:
            raise SubmissionPreflightError(
                "Explicit submission confirmation is required."
            )

        allow_resubmit = (
            body.get(
                "allow_resubmit",
                False,
            )
            is True
        )

        result = submit_artifact(
            artifact_hash,
            allow_resubmit=allow_resubmit,
        )

        return _emit(
            {
                "ok": True,
                "result": result,
            }
        )

    except SubmissionConflictError as exc:
        return _emit(
            {
                "ok": False,
                "http_status": 409,
                "state": "ready",
                "error": str(exc),
            }
        )

    except SubmissionRejectedError as exc:
        return _emit(
            {
                "ok": False,
                "http_status": 422,
                "state": "rejected",
                "error": str(exc),
            }
        )

    except SubmissionPreflightError as exc:
        return _emit(
            {
                "ok": False,
                "http_status": 400,
                "state": "failed",
                "error": str(exc),
            }
        )

    except SubmissionError:
        return _emit(
            {
                "ok": False,
                "http_status": 503,
                "state": "failed",
                "error": "Artifact submission failed.",
            }
        )


if __name__ == "__main__":
    raise SystemExit(main())