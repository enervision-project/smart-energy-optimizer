"""Tests de l'imputation de la consommation ; PostgreSQL isolé via TEST_DATABASE_URL."""

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
from etl_worker.transform import aggregate_hour, impute_consumption

T0 = datetime(2026, 10, 26, 10, tzinfo=UTC)


class ImputeConsumptionConfigurationTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.transform.psycopg.connect")
    def test_requires_database_configuration(self, connect):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            impute_consumption(minutes=15, end_time=T0)
        connect.assert_not_called()

    @patch("etl_worker.transform.psycopg.connect")
    def test_rejects_invalid_window_before_connecting(self, connect):
        with self.assertRaisesRegex(ValueError, "minutes"):
            impute_consumption("postgresql://test", minutes=0, end_time=T0)
        with self.assertRaisesRegex(ValueError, "fuseau"):
            impute_consumption("postgresql://test", minutes=15, end_time=T0.replace(tzinfo=None))
        connect.assert_not_called()

    @patch("etl_worker.transform.datetime")
    @patch("etl_worker.transform.psycopg.connect")
    def test_window_ends_now_by_default(self, connect, clock):
        clock.now.return_value = T0
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 4

        self.assertEqual(impute_consumption("postgresql://test", minutes=15), 4)

        parameters = cursor.execute.call_args.args[1]
        self.assertEqual(parameters["start"], T0 - timedelta(minutes=15))
        self.assertEqual(parameters["end"], T0)
        self.assertEqual(parameters["stable"], ["datacenter", "hospital"])
        self.assertEqual(parameters["max_age"], timedelta(minutes=15))
        self.assertEqual(parameters["max_span"], timedelta(minutes=3))


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "Définir TEST_DATABASE_URL pour les tests PostgreSQL.",
)
class ImputeConsumptionPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema_name = f"test_impute_{uuid4().hex}"
        self.connection = psycopg.connect(base_url, autocommit=True, row_factory=dict_row)
        self.addCleanup(self.connection.close)
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name)),
        )
        self.connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name)))
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
                source TEXT NOT NULL DEFAULT 'current' CHECK (source IN ('current', 'readings', 'backfill')),
                consumption_kw_imputed DOUBLE PRECISION,
                imputation_method TEXT CHECK (imputation_method IN ('previous_value', 'linear')),
                CHECK (
                    (consumption_kw_imputed IS NULL) = (imputation_method IS NULL)
                    AND (consumption_kw IS NULL OR consumption_kw_imputed IS NULL)
                ),
                PRIMARY KEY (site_id, ts)
            );
            CREATE TABLE readings_hours (
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                ts TIMESTAMPTZ NOT NULL, consumption_kwh NUMERIC(14, 2),
                voltage_v NUMERIC(14, 2), current_a NUMERIC(14, 2),
                power_factor NUMERIC(14, 2), temperature_celsius NUMERIC(14, 2),
                humidity_percent NUMERIC(14, 2),
                minutes_received SMALLINT, minutes_consumption SMALLINT,
                minutes_backfilled SMALLINT,
                PRIMARY KEY (site_id, ts)
            );
        """)
        self.database_url = make_conninfo(base_url, options=f"-c search_path={schema_name}")
        load_sites([
            {"site_id": "SITE001", "site_name": "Bureau", "site_type": "office",
             "capacity_kw": 200.0, "status": "active"},
            {"site_id": "SITE003", "site_name": "Datacenter", "site_type": "datacenter",
             "capacity_kw": 800.0, "status": "active"},
        ], self.database_url)

    def load(self, site_id, values):
        """values : minute depuis T0 → consommation (None = capteur en panne)."""
        load_readings([{
            "site_id": site_id,
            "timestamp": T0 + timedelta(minutes=minute),
            "site_type": None,
            "consumption_kw": kw,
            "consumption_kwh": kw,
            "null_reasons": [] if kw is not None else ["sensor_failure"],
            "data_quality": "good" if kw is not None else "partial",
        } for minute, kw in values.items()], self.database_url)

    def impute(self, minutes=60, end_minute=60):
        return impute_consumption(
            self.database_url, minutes=minutes, end_time=T0 + timedelta(minutes=end_minute)
        )

    def stored(self, site_id):
        rows = self.connection.execute(
            "SELECT ts, consumption_kw, consumption_kw_imputed, imputation_method "
            "FROM readings_raws WHERE site_id = %s ORDER BY ts",
            (site_id,),
        ).fetchall()
        return {int((row["ts"] - T0).total_seconds() // 60): row for row in rows}

    def test_short_outage_is_interpolated_and_raw_null_kept(self):
        self.load("SITE001", {0: 100.0, 1: None, 2: None, 3: 130.0})

        self.assertEqual(self.impute(), 2)

        rows = self.stored("SITE001")
        self.assertEqual([rows[m]["consumption_kw_imputed"] for m in (1, 2)], [110.0, 120.0])
        self.assertEqual({rows[m]["imputation_method"] for m in (1, 2)}, {"linear"})
        self.assertIsNone(rows[1]["consumption_kw"])
        self.assertIsNone(rows[0]["consumption_kw_imputed"])
        self.assertIsNone(rows[3]["imputation_method"])

    def test_three_missing_minutes_are_left_null(self):
        self.load("SITE001", {0: 100.0, 1: None, 2: None, 3: None, 4: 140.0})

        self.assertEqual(self.impute(), 0)

    def test_absent_minute_counts_as_missing(self):
        # Minute 1 jamais reçue : 0 et 3 encadrent toujours la minute 2.
        self.load("SITE001", {0: 100.0, 2: None, 3: 130.0})
        self.assertEqual(self.impute(), 1)
        self.assertEqual(self.stored("SITE001")[2]["consumption_kw_imputed"], 120.0)

        self.connection.execute("TRUNCATE readings_raws")
        self.load("SITE001", {0: 100.0, 2: None, 3: None, 4: 140.0})
        self.assertEqual(self.impute(), 0)

    def test_interpolation_waits_for_the_next_value(self):
        self.load("SITE001", {0: 100.0, 1: None})
        self.assertEqual(self.impute(end_minute=2), 0)

        self.load("SITE001", {2: 120.0})
        self.assertEqual(self.impute(end_minute=3), 1)
        self.assertEqual(self.stored("SITE001")[1]["consumption_kw_imputed"], 110.0)

    def test_stable_site_repeats_previous_value_for_fifteen_minutes(self):
        self.load("SITE003", {0: 500.0} | {minute: None for minute in range(1, 18)})

        self.assertEqual(self.impute(), 15)

        rows = self.stored("SITE003")
        self.assertEqual({rows[m]["consumption_kw_imputed"] for m in range(1, 16)}, {500.0})
        self.assertEqual({rows[m]["imputation_method"] for m in range(1, 16)}, {"previous_value"})
        # Jamais à partir d'une valeur imputée : au-delà de 15 min, NULL conservé.
        self.assertIsNone(rows[16]["consumption_kw_imputed"])
        self.assertIsNone(rows[17]["imputation_method"])

    def test_without_previous_raw_value_nothing_is_imputed(self):
        self.load("SITE001", {0: None, 1: 100.0})
        self.load("SITE003", {0: None})

        self.assertEqual(self.impute(), 0)

    def test_rerun_keeps_existing_imputations(self):
        self.load("SITE003", {0: 500.0, 1: None})
        self.impute()
        self.connection.execute(
            "UPDATE readings_raws SET consumption_kw = 900 WHERE ts = %s", (T0,)
        )

        self.assertEqual(self.impute(), 0)
        self.assertEqual(self.stored("SITE003")[1]["consumption_kw_imputed"], 500.0)

    def test_only_rows_inside_the_window_are_imputed(self):
        self.load("SITE003", {0: 500.0, 1: None, 10: None})

        self.assertEqual(self.impute(minutes=5, end_minute=12), 1)

        rows = self.stored("SITE003")
        self.assertIsNone(rows[1]["consumption_kw_imputed"])
        self.assertEqual(rows[10]["consumption_kw_imputed"], 500.0)

    def test_imputed_values_are_rounded_to_two_decimals(self):
        self.load("SITE001", {0: 100.0, 1: None, 2: None, 3: 101.0})

        self.impute()

        self.assertEqual(self.stored("SITE001")[1]["consumption_kw_imputed"], 100.33)

    def test_hourly_energy_ignores_imputed_values(self):
        self.load("SITE003", {0: 600.0, 1: None, 2: 300.0})
        self.impute()

        aggregate_hour(self.database_url, end_time=T0 + timedelta(hours=1))

        row = self.connection.execute(
            "SELECT consumption_kwh, minutes_received, minutes_consumption "
            "FROM readings_hours WHERE site_id = 'SITE003'"
        ).fetchone()
        self.assertEqual(row["consumption_kwh"], Decimal("450.00"))
        self.assertEqual((row["minutes_received"], row["minutes_consumption"]), (3, 2))
