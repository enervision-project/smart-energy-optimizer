"""Tests du load des alertes dans PostgreSQL, via un schéma temporaire isolé."""

import io
import os
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from etl_worker.load import alerts_main, load_alerts

ALERT = {
    "alert_id": "ALR-SITE001-1792569147",
    "timestamp": "2026-10-21T07:29:27.821005",
    "site_id": "SITE001",
    "severity": "critical",
    "type": "outage",
    "message": "Surcharge détectée sur le site d'essai",
    "value": 778.97123456789,
    "threshold": 630.0123456789,
}


class LoadAlertsConfigurationTests(unittest.TestCase):
    @patch("etl_worker.load.psycopg.connect")
    def test_empty_batch_does_not_connect(self, connect):
        self.assertEqual(load_alerts([]), 0)
        connect.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.load.psycopg.connect")
    def test_missing_url_fails_before_connecting(self, connect):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            load_alerts([ALERT])
        connect.assert_not_called()

    @patch("etl_worker.load.psycopg.connect")
    def test_invalid_timestamp_fails_before_connecting(self, connect):
        for timestamp in (None, "", "not-a-date"):
            with (
                self.subTest(timestamp=timestamp),
                self.assertRaisesRegex(ValueError, "Timestamp"),
            ):
                load_alerts([ALERT | {"timestamp": timestamp}], "postgresql://test")
        connect.assert_not_called()

    @patch("etl_worker.load.psycopg.connect")
    def test_missing_field_cannot_be_silently_replaced(self, connect):
        for field in ALERT:
            with self.subTest(field=field):
                incomplete = {
                    key: value for key, value in ALERT.items() if key != field
                }
                with self.assertRaises(KeyError):
                    load_alerts([ALERT, incomplete], "postgresql://test")
        connect.assert_not_called()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured-db/test"})
    @patch("etl_worker.load.psycopg.connect")
    def test_environment_and_connection_timeout_are_used(self, connect):
        connect.side_effect = psycopg.OperationalError("Connection refused")
        with self.assertRaises(psycopg.OperationalError):
            load_alerts([ALERT], connect_timeout=2)
        connect.assert_called_once_with(
            "postgresql://configured-db/test", connect_timeout=2
        )


class SyncAlertsCommandTests(unittest.TestCase):
    @patch("sys.argv", ["etl-sync-alerts"])
    @patch("etl_worker.load.load_alerts")
    @patch("etl_worker.load.extract_alerts")
    def test_extract_result_is_loaded_and_counts_are_printed(self, extract, load):
        alerts = [ALERT, ALERT | {"alert_id": "ALR-2"}]
        extract.return_value = alerts
        load.return_value = 1
        with redirect_stdout(io.StringIO()) as output:
            alerts_main()
        extract.assert_called_once_with()
        load.assert_called_once_with(alerts)
        self.assertIn(
            "Alertes reçues : 2 ; insérées : 1 ; déjà présentes : 1.", output.getvalue()
        )

    @patch("sys.argv", ["etl-sync-alerts"])
    @patch("etl_worker.load.load_alerts")
    @patch(
        "etl_worker.load.extract_alerts", side_effect=RuntimeError("API unavailable")
    )
    def test_failed_extract_cannot_reach_load(self, extract, load):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(RuntimeError):
            alerts_main()
        load.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    @patch("sys.argv", ["etl-sync-alerts"])
    @patch(
        "etl_worker.load.load_alerts",
        side_effect=psycopg.OperationalError("DB unavailable"),
    )
    @patch("etl_worker.load.extract_alerts", return_value=[ALERT])
    def test_failed_load_does_not_print_success(self, extract, load):
        with (
            redirect_stdout(io.StringIO()) as output,
            self.assertRaises(psycopg.OperationalError),
        ):
            alerts_main()
        self.assertEqual(output.getvalue(), "")


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Définir TEST_DATABASE_URL.")
class LoadAlertsPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema = f"test_alerts_{uuid4().hex}"
        self.connection = psycopg.connect(
            base_url, autocommit=True, row_factory=dict_row
        )
        self.addCleanup(self.connection.close)
        self.connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)),
        )
        self.connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        self.connection.execute("""
            CREATE TABLE sites (site_id TEXT PRIMARY KEY);
            INSERT INTO sites VALUES ('SITE001'), ('SITE002');
            CREATE TABLE alerts (
                alert_id TEXT PRIMARY KEY,
                "timestamp" TIMESTAMPTZ NOT NULL,
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                severity TEXT NOT NULL, type TEXT NOT NULL, message TEXT NOT NULL,
                value DOUBLE PRECISION, threshold DOUBLE PRECISION NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        self.database_url = make_conninfo(base_url, options=f"-c search_path={schema}")

    def rows(self):
        return self.connection.execute(
            "SELECT * FROM alerts ORDER BY alert_id"
        ).fetchall()

    def test_inserts_all_fields_without_rounding_or_mutating_input(self):
        alerts = [deepcopy(ALERT)]
        before = deepcopy(alerts)

        self.assertEqual(load_alerts(alerts, self.database_url), 1)

        expected = ALERT | {
            "timestamp": datetime.fromisoformat(ALERT["timestamp"]).replace(tzinfo=UTC)
        }
        row = self.rows()[0]
        self.assertEqual({key: row[key] for key in ALERT}, expected)
        self.assertIsNotNone(row["loaded_at"])
        self.assertEqual(alerts, before)

    def test_naive_timestamp_is_utc_and_displayed_in_paris(self):
        self.connection.execute("SET TIME ZONE 'Europe/Paris'")
        load_alerts([ALERT], self.database_url)
        row = self.connection.execute(
            'SELECT "timestamp", "timestamp"::text AS displayed FROM alerts'
        ).fetchone()
        self.assertEqual(
            row["timestamp"], datetime.fromisoformat("2026-10-21T07:29:27.821005+00:00")
        )
        self.assertEqual(row["displayed"], "2026-10-21 09:29:27.821005+02")

    def test_explicit_offsets_and_z_preserve_the_same_instant(self):
        alerts = [
            ALERT
            | {
                "alert_id": "ALR-OFFSET",
                "timestamp": "2026-10-21T09:29:27.821005+02:00",
            },
            ALERT | {"alert_id": "ALR-Z", "timestamp": "2026-10-21T07:29:27.821005Z"},
        ]
        self.assertEqual(load_alerts(alerts, self.database_url), 2)
        self.assertEqual(self.rows()[0]["timestamp"], self.rows()[1]["timestamp"])
        self.assertEqual(
            self.rows()[0]["timestamp"],
            datetime.fromisoformat("2026-10-21T07:29:27.821005+00:00"),
        )

    def test_winter_uses_paris_offset_without_changing_the_instant(self):
        self.connection.execute("SET TIME ZONE 'Europe/Paris'")
        load_alerts(
            [ALERT | {"timestamp": "2026-01-21T07:29:27.821005"}], self.database_url
        )
        row = self.connection.execute(
            'SELECT "timestamp"::text AS displayed FROM alerts'
        ).fetchone()
        self.assertEqual(row["displayed"], "2026-01-21 08:29:27.821005+01")

    def test_existing_id_keeps_its_content_and_first_loaded_at(self):
        load_alerts([ALERT], self.database_url)
        self.connection.execute(
            "UPDATE alerts SET loaded_at = %s",
            (datetime(2000, 1, 1, tzinfo=UTC),),
        )
        before = self.rows()
        modified = ALERT | {"message": "Nouvelle version", "value": None}

        self.assertEqual(load_alerts([modified], self.database_url), 0)

        self.assertEqual(self.rows(), before)

    def test_repeated_id_in_one_batch_keeps_only_the_first_version(self):
        modified = ALERT | {"value": 0.0}
        self.assertEqual(load_alerts([ALERT, modified, ALERT], self.database_url), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["value"], ALERT["value"])

    def test_mixed_batch_only_inserts_new_ids(self):
        load_alerts([ALERT], self.database_url)
        before = self.rows()[0]
        new = ALERT | {"alert_id": "ALR-NEW", "site_id": "SITE002"}

        self.assertEqual(load_alerts([ALERT, new, new], self.database_url), 1)

        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(
            next(row for row in self.rows() if row["alert_id"] == ALERT["alert_id"]),
            before,
        )

    def test_null_and_zero_are_kept_as_distinct_values(self):
        alerts = [
            ALERT | {"alert_id": "ALR-NULL", "value": None},
            ALERT | {"alert_id": "ALR-ZERO", "value": 0.0},
        ]
        self.assertEqual(load_alerts(alerts, self.database_url), 2)
        rows = self.rows()
        self.assertIsNone(rows[0]["value"])
        self.assertEqual(rows[1]["value"], 0.0)

    def test_unknown_site_rolls_back_the_entire_batch(self):
        load_alerts([ALERT], self.database_url)
        before = self.rows()
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            load_alerts(
                [
                    ALERT | {"alert_id": "ALR-NEW"},
                    ALERT | {"alert_id": "ALR-UNKNOWN", "site_id": "UNKNOWN"},
                ],
                self.database_url,
            )
        self.assertEqual(self.rows(), before)

    def test_required_field_error_rolls_back_new_rows(self):
        with self.assertRaises(psycopg.errors.NotNullViolation):
            load_alerts(
                [ALERT, ALERT | {"alert_id": "ALR-INVALID", "threshold": None}],
                self.database_url,
            )
        self.assertEqual(self.rows(), [])
