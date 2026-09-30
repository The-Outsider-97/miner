"""Small Miner-owned ledger for Harnyx artifact submissions."""

from __future__ import annotations

import sqlite3
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils.config_loader import get_config_section
from ..utils.miner_helpers import PROJECT_ROOT


class SubmissionLedger:
    def __init__(self) -> None:
        config = get_config_section("submission")

        self.path = (
            PROJECT_ROOT
            / str(
                config.get(
                    "ledger_path",
                    "state/submissions.sqlite3",
                )
            )
        ).resolve()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")

        self._create_schema()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_hash TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    platform_artifact_id TEXT,
                    platform_content_hash TEXT,
                    uid INTEGER,
                    size_bytes INTEGER,
                    submitted_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS
                idx_submissions_artifact_hash
                ON submissions(
                    artifact_hash,
                    submitted_at DESC
                );

                CREATE TABLE IF NOT EXISTS submission_locks(
                    artifact_hash TEXT PRIMARY KEY,
                    acquired_epoch INTEGER NOT NULL
                );
                """
            )

    def latest_upload(self, artifact_hash: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT
                artifact_hash,
                profile,
                status,
                platform_artifact_id,
                platform_content_hash,
                uid,
                size_bytes,
                submitted_at
            FROM submissions
            WHERE artifact_hash = ?
            ORDER BY submitted_at DESC
            LIMIT 1
            """,
            (artifact_hash,),
        ).fetchone()

        return dict(row) if row is not None else None

    def acquire_lock(self, artifact_hash: str, *, stale_after_seconds: int = 300) -> bool:
        now = int(time.time())
        threshold = now - stale_after_seconds

        try:
            with self.connection:
                self.connection.execute(
                    """
                    DELETE FROM submission_locks
                    WHERE acquired_epoch < ?
                    """,
                    (threshold,),
                )

                self.connection.execute(
                    """
                    INSERT INTO submission_locks(
                        artifact_hash,
                        acquired_epoch
                    )
                    VALUES(?, ?)
                    """,
                    (
                        artifact_hash,
                        now,
                    ),
                )

            return True

        except sqlite3.IntegrityError:
            return False

    def release_lock(self, artifact_hash: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM submission_locks
                WHERE artifact_hash = ?
                """,
                (artifact_hash,))

    def record_upload(
        self,
        *,
        artifact_hash: str,
        profile: str,
        platform_artifact_id: str | None,
        platform_content_hash: str | None,
        uid: int | None,
        size_bytes: int | None,
        submitted_at: str | None,
    ) -> None:
        timestamp = (submitted_at or datetime.now(timezone.utc).isoformat())

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO submissions(
                    artifact_hash,
                    profile,
                    status,
                    platform_artifact_id,
                    platform_content_hash,
                    uid,
                    size_bytes,
                    submitted_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_hash,
                    profile,
                    "uploaded_unconfirmed",
                    platform_artifact_id,
                    platform_content_hash,
                    uid,
                    size_bytes,
                    timestamp,
                ),
            )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SubmissionLedger":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False