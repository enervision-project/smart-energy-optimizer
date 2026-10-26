"""Accès SQL pour les snapshots, les jobs et les prévisions."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import pandas as pd
import psycopg


@dataclass(frozen=True)
class SiteProfile:
    site_id: str
    working_hour_start: int
    working_hour_end: int
    working_days: tuple[int, ...]


@contextmanager
def claimed_job(
    database_url: str, job_type: str, schedule_key: str, trigger: str
) -> Iterator[UUID | None]:
    """Une seule exécution par type et créneau, même après un redémarrage."""
    lock_key = 576_000 + (1 if job_type == "training" else 2)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
        if not cursor.fetchone()[0]:
            yield None
            return
        try:
            cursor.execute(
                """
                    INSERT INTO prediction_jobs(job_type, schedule_key, trigger_type, status)
                    VALUES (%s, %s, %s, 'running')
                    ON CONFLICT (job_type, schedule_key) DO UPDATE SET
                        status = 'running', trigger_type = EXCLUDED.trigger_type,
                        started_at = now(), finished_at = NULL, detail = NULL
                    WHERE prediction_jobs.status = 'failed'
                       OR (prediction_jobs.status = 'running'
                           AND prediction_jobs.started_at < now() - interval '6 hours')
                    RETURNING job_id
                    """,
                (job_type, schedule_key, trigger),
            )
            row = cursor.fetchone()
            connection.commit()
            if row is None:
                yield None
                return
            job_id = row[0]
            if job_type == "forecast":
                cursor.execute(
                    "SELECT 1 FROM prediction_runs WHERE job_id = %s AND status = 'complete'",
                    (job_id,),
                )
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE prediction_jobs SET status='succeeded', finished_at=now() "
                        "WHERE job_id=%s",
                        (job_id,),
                    )
                    connection.commit()
                    yield None
                    return
            try:
                yield job_id
            except Exception as exc:
                with connection.cursor() as update:
                    update.execute(
                        "UPDATE prediction_jobs SET status='failed', finished_at=now(), "
                        "detail=%s WHERE job_id=%s",
                        (str(exc)[:1000], job_id),
                    )
                connection.commit()
                raise
            else:
                with connection.cursor() as update:
                    update.execute(
                        "UPDATE prediction_jobs SET status='succeeded', "
                        "finished_at=now() WHERE job_id=%s",
                        (job_id,),
                    )
                connection.commit()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
            connection.commit()


def read_recent_hours(database_url: str, before: datetime) -> pd.DataFrame:
    """Snapshot cohérent des heures terminées ; exclut les cibles NULL."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT site_id, ts, consumption_kwh
                FROM readings_hours
                WHERE ts < %s AND consumption_kwh IS NOT NULL
                ORDER BY ts, site_id
                """,
            (before,),
        )
        rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=["site_id", "timestamp", "consumption_kwh"])


def read_site_profiles(database_url: str) -> list[SiteProfile]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT s.site_id, p.working_hour_start, p.working_hour_end, p.working_days
                FROM sites s JOIN site_profiles p USING(site_id)
                ORDER BY s.site_id
                """
        )
        return [SiteProfile(row[0], row[1], row[2], tuple(row[3])) for row in cursor.fetchall()]


def latest_hour(database_url: str) -> datetime | None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT max(ts) FROM readings_hours WHERE consumption_kwh IS NOT NULL")
        return cursor.fetchone()[0]


def save_forecast(
    database_url: str,
    job_id: UUID,
    model_name: str,
    model_version: str,
    hours: Sequence[datetime],
    rows: Sequence[tuple[str, datetime, float]],
    site_count: int,
) -> UUID:
    """Publie le lot complet et ses lignes en une transaction."""
    if not hours or not rows or len(rows) != site_count * len(hours):
        raise ValueError("Lot de prévisions incomplet.")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO prediction_runs
                    (job_id, model_name, model_version, window_start, window_end,
                     site_count, prediction_count, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'complete')
                RETURNING run_id
                """,
                (
                    job_id,
                    model_name,
                    model_version,
                    hours[0],
                    hours[-1] + timedelta(hours=1),
                    site_count,
                    len(rows),
                ),
            )
            run_id = cursor.fetchone()[0]
            cursor.executemany(
                """
                INSERT INTO predictions(run_id, site_id, predicted_for, prediction_kwh)
                VALUES (%s, %s, %s, %s)
                """,
                [(run_id, site_id, hour, value) for site_id, hour, value in rows],
            )
        connection.commit()
    return run_id
