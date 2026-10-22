"""Tests du calcul horaire ; PostgreSQL isolé via TEST_DATABASE_URL."""

import os
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from etl_worker.load import load_readings, load_sites
from etl_worker.transform import aggregate_hour

START = datetime(2026, 10, 20, 11, tzinfo=UTC)
END = START + timedelta(hours=1, minutes=2)
METRICS = (
    "consumption_kwh", "voltage_v", "current_a", "power_factor",
    "temperature_celsius", "humidity_percent",
)


class AggregateHourConfigurationTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.transform.psycopg.connect")
    def test_requires_database_configuration(self, connect):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            aggregate_hour(end_time=END)
        connect.assert_not_called()

    @patch("etl_worker.transform.psycopg.connect")
    def test_rejects_naive_time_before_connecting(self, connect):
        naive_end_time = END.replace(tzinfo=None)
        with self.assertRaisesRegex(ValueError, "fuseau"):
            aggregate_hour("postgresql://test", end_time=naive_end_time)
        connect.assert_not_called()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured-db/test"})
    @patch("etl_worker.transform.psycopg.connect")
    def test_propagates_connection_failure(self, connect):
        connect.side_effect = psycopg.OperationalError("Connection refused")
        with self.assertRaises(psycopg.OperationalError):
            aggregate_hour(end_time=END, connect_timeout=2)
        connect.assert_called_once_with(
            "postgresql://configured-db/test", connect_timeout=2
        )

    @patch("etl_worker.transform.datetime")
    @patch("etl_worker.transform.psycopg.connect")
    def test_defaults_to_last_completed_utc_hour(self, connect, clock):
        clock.now.return_value = END.replace(second=59, microsecond=999)
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 2

        self.assertEqual(aggregate_hour("postgresql://test"), 2)

        clock.now.assert_called_once_with(UTC)
        self.assertEqual(
            cursor.execute.call_args.args[1],
            {"start": START, "end": START + timedelta(hours=1)},
        )


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "Définir TEST_DATABASE_URL pour les tests PostgreSQL.",
)
class AggregateHourPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema_name = f"test_hours_{uuid4().hex}"
        self.connection = psycopg.connect(
            base_url, autocommit=True, row_factory=dict_row
        )
        self.addCleanup(self.connection.close)
        self.connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name)),
        )
        self.connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
        )
        self.connection.execute("""
            CREATE TABLE sites (
                site_id TEXT PRIMARY KEY, site_name TEXT NOT NULL,
                site_type TEXT NOT NULL, location TEXT,
                capacity_kw DOUBLE PRECISION NOT NULL CHECK (capacity_kw > 0),
                status TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE readings_raws (
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                ts TIMESTAMPTZ NOT NULL, site_type TEXT,
                consumption_kw DOUBLE PRECISION, consumption_kwh DOUBLE PRECISION,
                voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
                power_factor DOUBLE PRECISION, temperature_celsius DOUBLE PRECISION,
                humidity_percent DOUBLE PRECISION,
                null_reasons TEXT[] NOT NULL DEFAULT '{}',
                data_quality TEXT NOT NULL, loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (site_id, ts)
            );
            CREATE TABLE readings_hours (
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                ts TIMESTAMPTZ NOT NULL, consumption_kwh NUMERIC(14, 2),
                voltage_v NUMERIC(14, 2), current_a NUMERIC(14, 2),
                power_factor NUMERIC(14, 2), temperature_celsius NUMERIC(14, 2),
                humidity_percent NUMERIC(14, 2), PRIMARY KEY (site_id, ts)
            );
        """)
        self.database_url = make_conninfo(
            base_url, options=f"-c search_path={schema_name}"
        )
        self.start = START
        self.add_site("SITE001")

    def add_site(self, site_id):
        load_sites([{
            "site_id": site_id, "site_name": site_id, "site_type": "office",
            "capacity_kw": 200.0, "status": "active",
        }], self.database_url)

    def readings(self, minutes=range(60), site_id="SITE001"):
        return [{
            "site_id": site_id,
            "timestamp": self.start + timedelta(minutes=minute),
            "site_type": "office",
            "consumption_kw": 120.0,
            # Valeur volontairement différente : l'énergie utilise les kW.
            "consumption_kwh": 9999.0,
            "voltage_v": 220.0,
            "current_a": 10.0,
            "power_factor": 0.9,
            "temperature_celsius": 20.0,
            "humidity_percent": 40.0,
            "null_reasons": [],
            "data_quality": "good",
        } for minute in minutes]

    def stored_hours(self):
        return self.connection.execute(
            "SELECT * FROM readings_hours ORDER BY ts, site_id"
        ).fetchall()

    def test_complete_hour_integrates_kw_and_keeps_raw_data_unchanged(self):
        readings = self.readings()
        for index, reading in enumerate(readings):
            reading["consumption_kw"] = 60.0 if index < 30 else 180.0
        load_readings(readings, self.database_url)
        before = self.connection.execute(
            "SELECT * FROM readings_raws ORDER BY site_id, ts"
        ).fetchall()

        self.assertEqual(aggregate_hour(self.database_url, end_time=END), 1)

        row = self.stored_hours()[0]
        self.assertEqual(row["ts"], START)
        self.assertAlmostEqual(row["consumption_kwh"], 120.0)
        for field in METRICS[1:]:
            self.assertEqual(row[field], Decimal(str(readings[0][field])))
        after = self.connection.execute(
            "SELECT * FROM readings_raws ORDER BY site_id, ts"
        ).fetchall()
        self.assertEqual(after, before)

    def test_each_average_uses_its_own_non_null_values(self):
        readings = self.readings()
        for index, reading in enumerate(readings):
            reading["voltage_v"] = 200.0 + index if index < 45 else None
            reading["current_a"] = index + 1.0 if index < 30 else None
            reading["power_factor"] = 0.9 if index >= 15 else None
            reading["temperature_celsius"] = None
            reading["humidity_percent"] = 40.0 if index < 30 else None
            reading["data_quality"] = "critical"
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        self.assertAlmostEqual(row["voltage_v"], 222.0)  # 45 valeurs, pas 60.
        self.assertAlmostEqual(row["current_a"], 15.5)
        self.assertEqual(row["power_factor"], Decimal("0.90"))
        self.assertIsNone(row["temperature_celsius"])
        self.assertAlmostEqual(row["humidity_percent"], 40.0)
        self.assertAlmostEqual(row["consumption_kwh"], 120.0)

    def test_fifteen_null_powers_use_the_45_available_values(self):
        readings = self.readings()
        for index, reading in enumerate(readings):
            reading["consumption_kw"] = None if index < 15 else float(index + 1)
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        # Moyenne des valeurs 16 à 60 : 38 kW, soit 38 kWh estimés sur 1 heure.
        self.assertEqual(row["consumption_kwh"], Decimal("38.00"))
        self.assertAlmostEqual(row["voltage_v"], 220.0)

    def test_incomplete_hour_estimates_from_available_minutes(self):
        load_readings(self.readings(range(41)), self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        self.assertEqual(self.stored_hours()[0]["consumption_kwh"], Decimal("120.00"))

    def test_all_null_powers_keep_energy_null_without_losing_averages(self):
        readings = self.readings()
        for reading in readings:
            reading["consumption_kw"] = None
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        self.assertIsNone(row["consumption_kwh"])
        self.assertEqual(row["voltage_v"], Decimal("220.00"))

    def test_zero_counts_as_valid_and_null_does_not(self):
        readings = self.readings()
        for reading in readings:
            reading["consumption_kw"] = None
        readings[0]["consumption_kw"] = 0.0
        readings[1]["consumption_kw"] = 120.0
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        self.assertEqual(self.stored_hours()[0]["consumption_kwh"], Decimal("60.00"))

    def test_window_includes_start_and_excludes_next_hour(self):
        readings = self.readings(range(-1, 61))
        readings[0]["consumption_kw"] = 10000.0
        readings[0]["voltage_v"] = 10000.0
        readings[-1]["consumption_kw"] = 10000.0
        readings[-1]["voltage_v"] = 10000.0
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        self.assertAlmostEqual(row["consumption_kwh"], 120.0)
        self.assertAlmostEqual(row["voltage_v"], 220.0)

    def test_zero_is_a_valid_measurement(self):
        readings = self.readings()
        for reading in readings:
            for field in ("consumption_kw",) + METRICS:
                reading[field] = 0.0
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        self.assertTrue(all(row[field] == 0.0 for field in METRICS))

    def test_site_without_measurements_gets_null_metrics(self):
        aggregate_hour(self.database_url, end_time=END)
        row = self.stored_hours()[0]
        self.assertTrue(all(row[field] is None for field in METRICS))

    def test_no_sites_means_no_hourly_rows(self):
        self.connection.execute("DELETE FROM sites")
        self.assertEqual(aggregate_hour(self.database_url, end_time=END), 0)
        self.assertEqual(self.stored_hours(), [])

    def test_sites_are_aggregated_independently(self):
        self.add_site("SITE002")
        readings = self.readings()
        second = self.readings(site_id="SITE002")
        for reading in second:
            reading["consumption_kw"] = 60.0
            reading["voltage_v"] = 240.0
        load_readings(readings + second, self.database_url)

        self.assertEqual(aggregate_hour(self.database_url, end_time=END), 2)

        first, second = self.stored_hours()
        self.assertAlmostEqual(first["consumption_kwh"], 120.0)
        self.assertAlmostEqual(second["consumption_kwh"], 60.0)
        self.assertAlmostEqual(second["voltage_v"], 240.0)

    def test_replay_updates_estimate_with_late_data_without_duplicates(self):
        first = self.readings(range(45))
        for reading in first:
            reading["consumption_kw"] = 60.0
        load_readings(first, self.database_url)
        aggregate_hour(self.database_url, end_time=END)
        self.assertEqual(self.stored_hours()[0]["consumption_kwh"], Decimal("60.00"))

        late = self.readings(range(45, 60))
        for reading in late:
            reading["consumption_kw"] = 180.0
        load_readings(late, self.database_url)
        aggregate_hour(self.database_url, end_time=END)
        aggregate_hour(self.database_url, end_time=END)

        rows = self.stored_hours()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["consumption_kwh"], Decimal("90.00"))

    def test_paris_reference_is_converted_to_utc(self):
        load_readings(self.readings(), self.database_url)

        aggregate_hour(
            self.database_url,
            end_time=datetime.fromisoformat("2026-10-20T14:02:59+02:00"),
        )

        row = self.stored_hours()[0]
        self.assertEqual(row["ts"], START)
        self.assertAlmostEqual(row["consumption_kwh"], 120.0)

    def test_repeated_paris_hour_at_dst_change_keeps_two_distinct_rows(self):
        self.start = datetime(2026, 10, 25, 0, tzinfo=UTC)
        load_readings(self.readings(), self.database_url)
        self.start += timedelta(hours=1)
        load_readings(self.readings(), self.database_url)

        for reference in ("2026-10-25T02:02:00+01:00", "2026-10-25T03:02:00+01:00"):
            aggregate_hour(
                self.database_url, end_time=datetime.fromisoformat(reference)
            )

        rows = self.stored_hours()
        self.assertEqual([row["ts"].astimezone(UTC).hour for row in rows], [0, 1])
        self.assertTrue(all(row["consumption_kwh"] == Decimal("120.00") for row in rows))

    def test_failure_rolls_back_all_sites(self):
        self.add_site("SITE002")
        load_readings(self.readings(), self.database_url)
        self.connection.execute(
            "ALTER TABLE readings_hours ALTER COLUMN consumption_kwh SET NOT NULL"
        )

        with self.assertRaises(psycopg.errors.NotNullViolation):
            aggregate_hour(self.database_url, end_time=END)

        self.assertEqual(self.stored_hours(), [])

    def test_rounds_all_results_to_two_decimals_only_after_aggregation(self):
        readings = self.readings()
        for index, reading in enumerate(readings):
            reading["consumption_kw"] = 1.0044 if index < 30 else 1.0054
            reading["voltage_v"] = 399.09649122807014
            reading["current_a"] = 0.0044 if index < 30 else 0.0054
            reading["power_factor"] = 0.935
            reading["temperature_celsius"] = -1.235
            reading["humidity_percent"] = 12.345
        load_readings(readings, self.database_url)

        aggregate_hour(self.database_url, end_time=END)

        row = self.stored_hours()[0]
        expected = {
            "consumption_kwh": Decimal("1.00"),
            "voltage_v": Decimal("399.10"),
            "current_a": Decimal("0.00"),
            "power_factor": Decimal("0.94"),
            "temperature_celsius": Decimal("-1.24"),
            "humidity_percent": Decimal("12.35"),
        }
        self.assertEqual({key: row[key] for key in METRICS}, expected)
        self.assertTrue(all(row[key].as_tuple().exponent == -2 for key in METRICS))
        raw = self.connection.execute(
            "SELECT voltage_v, current_a FROM readings_raws ORDER BY ts LIMIT 1"
        ).fetchone()
        self.assertEqual(raw, {
            "voltage_v": readings[0]["voltage_v"],
            "current_a": readings[0]["current_a"],
        })

    def test_paris_display_changes_with_season_without_moving_instants(self):
        self.connection.execute("SET TIME ZONE 'Europe/Paris'")
        cases = (
            (datetime(2026, 1, 20, 11, tzinfo=UTC), "2026-01-20 12:00:00+01"),
            (START, "2026-10-20 13:00:00+02"),
        )
        for start, displayed_time in cases:
            with self.subTest(start=start):
                self.start = start
                load_readings(self.readings(), self.database_url)
                aggregate_hour(
                    self.database_url, end_time=start + timedelta(hours=1, minutes=2)
                )
                row = self.connection.execute(
                    "SELECT ts, ts::text AS displayed FROM readings_hours WHERE ts = %s",
                    (start,),
                ).fetchone()
                self.assertEqual(row["ts"], start)
                self.assertEqual(row["displayed"], displayed_time)
