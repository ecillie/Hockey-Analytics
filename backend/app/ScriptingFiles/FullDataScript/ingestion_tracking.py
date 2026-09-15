"""Durable run records and overlap protection for ingestion stages."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import wraps
import hashlib
from typing import Any, TypeVar

from psycopg2.extras import Json

from app.database import connect_database


class ConcurrentIngestionError(RuntimeError):
    """Raised when the same ingestion stage is already running."""


Result = TypeVar("Result", bound=Mapping[str, Any])


def advisory_lock_key(job_name: str) -> int:
    raw = hashlib.sha256(f"tradevalue:{job_name}".encode()).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


def _record_count(summary: Mapping[str, Any]) -> int:
    dimensions = {"players", "teams", "cached", "profile_failures"}
    return sum(
        value
        for key, value in summary.items()
        if key not in dimensions and type(value) is int and value >= 0
    )


def tracked_ingestion(source_code: str, job_name: str | None = None):
    """Decorate a stage with a durable run row and a session advisory lock."""

    def decorate(function: Callable[..., Result]) -> Callable[..., Result]:
        resolved_job_name = job_name or function.__name__

        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Result:
            connection = connect_database()
            cursor = connection.cursor()
            run_id = None
            locked = False
            try:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s)",
                    (advisory_lock_key(resolved_job_name),),
                )
                locked = bool(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT id FROM data_sources WHERE code=%s",
                    (source_code,),
                )
                source = cursor.fetchone()
                if source is None:
                    raise RuntimeError(f"Unknown ingestion data source: {source_code}")
                cursor.execute(
                    """INSERT INTO ingestion_runs
                           (source_id,job_name,status,metadata,finished_at,error_message)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        source[0],
                        resolved_job_name,
                        "running" if locked else "cancelled",
                        Json({"started_by": "schema-native-loader"}),
                        None if locked else datetime.now(timezone.utc),
                        None if locked else "Another run already holds the ingestion lock",
                    ),
                )
                run_id = cursor.fetchone()[0]
                connection.commit()
                if not locked:
                    raise ConcurrentIngestionError(
                        f"Ingestion job {resolved_job_name!r} is already running"
                    )

                try:
                    summary = function(*args, **kwargs)
                except Exception as exc:
                    cursor.execute(
                        """UPDATE ingestion_runs SET status='failed',finished_at=CURRENT_TIMESTAMP,
                               error_message=%s WHERE id=%s""",
                        (str(exc)[:4000], run_id),
                    )
                    connection.commit()
                    raise

                records = int(summary.get("records_read", _record_count(summary)))
                created = int(summary.get("records_created", 0))
                updated = int(summary.get("records_updated", _record_count(summary)))
                skipped = int(summary.get("records_skipped", 0))
                cursor.execute(
                    """UPDATE ingestion_runs SET status='succeeded',finished_at=CURRENT_TIMESTAMP,
                           records_read=%s,records_created=%s,records_updated=%s,
                           records_skipped=%s,metadata=%s WHERE id=%s""",
                    (records, created, updated, skipped, Json(dict(summary)), run_id),
                )
                connection.commit()
                return summary
            finally:
                if locked:
                    # Clear any aborted control-connection transaction before
                    # releasing the session-level lock.
                    connection.rollback()
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (advisory_lock_key(resolved_job_name),),
                    )
                    connection.commit()
                cursor.close()
                connection.close()

        return wrapped

    return decorate
