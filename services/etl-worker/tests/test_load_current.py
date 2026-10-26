"""Complétion des consommations /current ; PostgreSQL isolé via TEST_DATABASE_URL."""

import io
import json
import os
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from etl_worker.bronze import write_readings_bronze
from etl_worker.load import load_readings, load_sites
from etl_worker.timestamps import parse_reading_timestamp

START = datetime(2026, 10, 26, 8, 3, 16, tzinfo=UTC)
MINUTE = START.replace(second=0)  # ts stocké : début de la minute


def reading(minute=0, site="SITE001", kw=None, kwh=None, **extra):
    return {
        "site_id": site, "site_type": "office",
        "timestamp": (START + timedelta(minutes=minute, microseconds=268687)).isoformat(),
        "consumption_kw": kw, "consumption_kwh": kwh,
        "voltage_v": None, "current_a": None, "power_factor": None,
        "temperature_celsius": None, "humidity_percent": None,
        "null_reasons": ["capteur défaillant"], "data_quality": "critical",
        **extra,
    }


class CurrentReadingUnitTests(unittest.TestCase):
    def test_timestamp_supports_api_utc_and_explicit_offsets_without_losing_precision(self):
        expected = START.replace(microsecond=268687)
        self.assertEqual(parse_reading_timestamp("2026-10-26T08:03:16.268687"), expected)
        self.assertEqual(parse_reading_timestamp("2026-10-26T09:03:16.268687+01:00"), expected)
        self.assertEqual(parse_reading_timestamp(expected), expected)
        for invalid in (None, "not a timestamp", 42):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parse_reading_timestamp(invalid)

    @patch("etl_worker.load.psycopg.connect")
    def test_only_missing_consumptions_change_on_a_copy(self, connect):
        source = reading(kw=0, data_quality="partial", extra={"value": None})
        before = deepcopy(source)
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (99.0, 0.25)
        cursor.rowcount = 1
        self.assertEqual(load_readings([source], "postgresql://fixture", fill_consumptions=True), 1)
        self.assertEqual(source, before)
        select_parameters = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(select_parameters, {"site_id": "SITE001", "ts": MINUTE})
        row = cursor.execute.call_args_list[-1].args[1]
        self.assertEqual(row[1], MINUTE)  # Secondes et fractions supprimées.
        self.assertEqual(row[3:5], (0, 0.25))
        self.assertTrue(all(value is None for value in row[5:10]))
        self.assertEqual(row[10:], (source["null_reasons"], "partial"))

    @patch("etl_worker.load.psycopg.connect")
    def test_absent_history_keeps_null_and_emits_a_warning(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (None, None)
        cursor.rowcount = 1
        with self.assertLogs("etl_worker.load", level="WARNING") as logs:
            load_readings([reading()], "postgresql://fixture", fill_consumptions=True)
        self.assertEqual(cursor.execute.call_args_list[-1].args[1][3:5], (None, None))
        self.assertEqual(len(logs.output), 2)


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Définir TEST_DATABASE_URL pour PostgreSQL.")
class CurrentReadingPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema = f"test_current_{uuid4().hex}"
        self.connection = psycopg.connect(base_url, autocommit=True, row_factory=dict_row)
        self.addCleanup(self.connection.close)
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)),
        )
        self.connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        self.connection.execute("""
            CREATE TABLE sites (
                site_id TEXT PRIMARY KEY, site_name TEXT NOT NULL, site_type TEXT NOT NULL,
                location TEXT, capacity_kw DOUBLE PRECISION CHECK (capacity_kw > 0),
                status TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE readings_raws (
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                ts TIMESTAMPTZ NOT NULL, site_type TEXT,
                consumption_kw DOUBLE PRECISION, consumption_kwh DOUBLE PRECISION,
                voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
                power_factor DOUBLE PRECISION, temperature_celsius DOUBLE PRECISION,
                humidity_percent DOUBLE PRECISION,
                null_reasons TEXT[] NOT NULL DEFAULT '{}', data_quality TEXT NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (site_id, ts)
            );
        """)
        self.database_url = make_conninfo(base_url, options=f"-c search_path={schema}")
        load_sites([
            {"site_id": site, "site_name": site, "site_type": "office",
             "capacity_kw": 100, "status": "active"}
            for site in ("SITE001", "SITE002")
        ], self.database_url)

    def stored(self):
        return self.connection.execute("SELECT * FROM readings_raws ORDER BY ts, site_id").fetchall()

    def load_current(self, readings):
        return load_readings(readings, self.database_url, fill_consumptions=True)

    def test_consecutive_nulls_survive_new_connections_and_never_borrow_another_site(self):
        self.load_current([reading(kw=12.5, kwh=0.2), reading(site="SITE002", kw=99, kwh=9)])
        for minute in range(1, 5):
            source = reading(minute)
            before = deepcopy(source)
            self.assertEqual(self.load_current([source]), 1)
            self.assertEqual(source, before)
        rows = [row for row in self.stored() if row["site_id"] == "SITE001"]
        self.assertEqual(len(rows), 5)
        self.assertTrue(all((row["consumption_kw"], row["consumption_kwh"]) == (12.5, 0.2) for row in rows))
        self.assertTrue(all(row["ts"].microsecond == 0 and row["ts"].second == 0 for row in rows))
        self.assertTrue(all(row["voltage_v"] is None and row["data_quality"] == "critical" for row in rows))

    def test_fields_use_their_own_last_non_null_value_and_received_values_win(self):
        load_readings([reading(kw=10, kwh=1), reading(1, kw=12)], self.database_url)
        self.load_current([reading(2, kwh=2), reading(3)])
        rows = self.stored()
        self.assertEqual(
            [(row["consumption_kw"], row["consumption_kwh"]) for row in rows],
            [(10, 1), (12, None), (12, 2), (12, 2)],
        )

    def test_does_not_borrow_a_future_value(self):
        load_readings([reading(kw=10, kwh=1), reading(4, kw=99, kwh=9)], self.database_url)
        self.load_current([reading(3)])
        self.assertEqual(
            (self.stored()[1]["consumption_kw"], self.stored()[1]["consumption_kwh"]), (10, 1),
        )

    def test_initial_nulls_remain_unknown_and_zero_is_available(self):
        with self.assertLogs("etl_worker.load", level="WARNING"):
            self.load_current([reading()])
        self.load_current([reading(1, kw=0, kwh=0), reading(2)])
        rows = self.stored()
        self.assertEqual((rows[0]["consumption_kw"], rows[0]["consumption_kwh"]), (None, None))
        self.assertEqual((rows[-1]["consumption_kw"], rows[-1]["consumption_kwh"]), (0, 0))

    def test_unsorted_batch_is_processed_chronologically_without_mutating_source(self):
        source = [reading(2), reading(kw=12.5, kwh=0.2), reading(1)]
        before = deepcopy(source)
        self.assertEqual(self.load_current(source), 3)
        self.assertEqual(source, before)
        self.assertTrue(all(row["consumption_kw"] == 12.5 for row in self.stored()))

    def test_timestamp_normalization_keeps_instants_and_deduplicates_same_minute(self):
        first = reading(kw=12.567891234, kwh=0.123456789,
                        timestamp="2026-10-26T09:03:16.268687+01:00")
        self.assertEqual(self.load_current([first]), 1)
        self.assertEqual(self.load_current([reading(kw=99, kwh=9,
                         timestamp="2026-10-26T08:03:16.999999")]), 0)
        # Autre seconde de la même minute : toujours ignorée, la première collecte reste.
        self.assertEqual(self.load_current([reading(kw=77, kwh=7,
                         timestamp="2026-10-26T08:03:48.5")]), 0)
        row = self.stored()[0]
        self.assertEqual(row["ts"], MINUTE)
        self.assertEqual((row["consumption_kw"], row["consumption_kwh"]), (12.567891234, 0.123456789))

    def test_failure_rolls_back_entire_batch(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.load_current([reading(kw=10, kwh=1), reading(1, site="UNKNOWN", kw=20, kwh=2)])
        self.assertEqual(self.stored(), [])

    def test_command_archives_originals_then_stores_only_the_transformed_copy(self):
        from etl_worker import __main__ as worker
        self.load_current([reading(kw=10, kwh=1)])
        source = [reading(1, timestamp="2026-10-26T08:04:16.998877", extra={"original": None})]
        before = deepcopy(source)
        client = MagicMock()

        def archive(values, **kwargs):
            return write_readings_bronze(values, "test-bucket", client=client, **kwargs)

        def load(values, **kwargs):
            return load_readings(values, self.database_url, **kwargs)

        with (
            patch.object(worker, "_require_site_ids", return_value=["SITE001"]),
            patch.object(worker, "extract_readings", return_value=source),
            patch.object(worker, "write_readings_bronze", side_effect=archive),
            patch.object(worker, "load_readings", side_effect=load),
            redirect_stdout(io.StringIO()),
        ):
            worker.cmd_sync_readings(Namespace())
        archived = [json.loads(line) for line in client.put_object.call_args.kwargs["Body"].decode().splitlines()]
        self.assertEqual(archived, before)
        self.assertEqual(source, before)
        stored = self.stored()[-1]
        self.assertEqual(stored["ts"], MINUTE + timedelta(minutes=1))
        # sync-readings n'active pas la complétion : le NULL reçu est stocké tel quel.
        self.assertEqual((stored["consumption_kw"], stored["consumption_kwh"]), (None, None))
        self.assertIsNone(stored["voltage_v"])
        self.assertEqual(stored["null_reasons"], before[0]["null_reasons"])


if __name__ == "__main__":
    unittest.main()
