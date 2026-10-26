from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from prediction_service import repository


def test_forecast_batch_is_complete_and_committed_once(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, parameters):
            connection.statements.append((sql, parameters))

        def fetchone(self):
            return (UUID(int=9),)

        def executemany(self, sql, rows):
            connection.rows = rows

    class Connection:
        def __init__(self):
            self.statements = []
            self.rows = []
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

        def commit(self):
            self.commits += 1

    connection = Connection()
    monkeypatch.setattr(repository.psycopg, "connect", lambda _url: connection)
    hours = [datetime(2026, 10, 26, 2, tzinfo=UTC) + timedelta(hours=i) for i in range(24)]
    rows = [("SITE001", hour, 12.0) for hour in hours]
    with pytest.raises(ValueError, match="incomplet"):
        repository.save_forecast("db", UUID(int=1), "hourly", "7", hours, rows[:-1], 1)
    assert not connection.statements

    run_id = repository.save_forecast("db", UUID(int=1), "hourly", "7", hours, rows, 1)
    assert run_id == UUID(int=9)
    assert connection.statements[0][1][3:5] == (
        hours[0],
        hours[-1] + timedelta(hours=1),
    )
    assert len(connection.rows) == 24
    assert all(row[0] == run_id for row in connection.rows)
    assert connection.commits == 1


def test_claimed_job_marks_success_and_failure(monkeypatch):
    class Cursor:
        def __init__(self):
            self.sql = ""
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _parameters):
            self.sql = sql
            self.statements.append(sql)

        def fetchone(self):
            if "pg_try_advisory_lock" in self.sql:
                return (True,)
            if "INSERT INTO prediction_jobs" in self.sql:
                return (UUID(int=3),)
            return None

    class Connection:
        def __init__(self):
            self.db_cursor = Cursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.db_cursor

        def commit(self):
            self.commits += 1

    connection = Connection()
    monkeypatch.setattr(repository.psycopg, "connect", lambda _url: connection)
    with repository.claimed_job("db", "training", "2026-10-26", "scheduled") as job_id:
        assert job_id == UUID(int=3)
    assert any("status='succeeded'" in sql for sql in connection.db_cursor.statements)
    assert any("pg_advisory_unlock" in sql for sql in connection.db_cursor.statements)

    connection = Connection()
    with (
        pytest.raises(RuntimeError, match="training failed"),
        repository.claimed_job("db", "training", "2026-10-27", "scheduled"),
    ):
        raise RuntimeError("training failed")
    assert any("status='failed'" in sql for sql in connection.db_cursor.statements)
    assert any("pg_advisory_unlock" in sql for sql in connection.db_cursor.statements)
