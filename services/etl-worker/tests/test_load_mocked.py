"""Tests du chargement avec une connexion PostgreSQL simulée."""

import os
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from etl_worker.load import load_alerts, load_readings, load_sites, read_site_ids

SITE = {
    "site_id": "SITE001",
    "site_name": "Bureau Paris La Défense",
    "site_type": "office",
    "capacity_kw": 200.0,
    "status": "active",
}
READING = {
    "site_id": "SITE001",
    "timestamp": "2026-10-21T08:08:00+00:00",
    "site_type": "office",
    "consumption_kw": 12.5,
    "data_quality": "good",
}
ALERT = {
    "alert_id": "ALR-1",
    "timestamp": "2026-10-21T07:06:22",
    "site_id": "SITE001",
    "severity": "critical",
    "type": "outage",
    "message": "Surcharge",
    "value": None,
    "threshold": 270.5,
}
DATABASE_URL = "postgresql://db.test/enervision"


def mock_connection(mock_connect, rowcount=0, rows=()):
    cursor = MagicMock(rowcount=rowcount)
    cursor.fetchall.return_value = list(rows)
    connection = mock_connect.return_value.__enter__.return_value
    connection.cursor.return_value.__enter__.return_value = cursor
    return cursor


@patch("etl_worker.load.psycopg.connect")
class LoadMockedTests(unittest.TestCase):
    def test_load_sites_returns_rowcount(self, mock_connect):
        cursor = mock_connection(mock_connect, rowcount=1)

        self.assertEqual(load_sites([SITE], DATABASE_URL), 1)

        rows = cursor.executemany.call_args.args[1]
        self.assertEqual(rows, [("SITE001", "Bureau Paris La Défense", "office", None, 200.0, "active")])

    def test_load_readings_keeps_missing_values_as_null(self, mock_connect):
        cursor = mock_connection(mock_connect, rowcount=1)

        self.assertEqual(load_readings([READING], DATABASE_URL, connect_timeout=3), 1)

        mock_connect.assert_called_once_with(DATABASE_URL, connect_timeout=3)
        row = cursor.executemany.call_args.args[1][0]
        self.assertEqual(
            row,
            ("SITE001", datetime.fromisoformat(READING["timestamp"]), "office", 12.5, None, None, None, None,
             None, None, [], "good"),
        )

    def test_load_readings_empty_batch_does_not_connect(self, mock_connect):
        self.assertEqual(load_readings([]), 0)
        mock_connect.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_configuration_fails_before_connecting(self, mock_connect):
        for function, payload in (
            (load_readings, [READING]),
            (load_alerts, [ALERT]),
        ):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(
                ValueError, "DATABASE_URL"
            ):
                function(payload)
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            read_site_ids()
        mock_connect.assert_not_called()

    @patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL})
    def test_read_site_ids_returns_first_column(self, mock_connect):
        mock_connection(mock_connect, rows=[("SITE001",), ("SITE002",)])

        self.assertEqual(read_site_ids(), ["SITE001", "SITE002"])

    def test_load_alerts_normalizes_timestamp_to_utc(self, mock_connect):
        cursor = mock_connection(mock_connect, rowcount=1)

        self.assertEqual(load_alerts([ALERT], DATABASE_URL), 1)

        row = cursor.executemany.call_args.args[1][0]
        self.assertEqual(row[1], datetime(2026, 10, 21, 7, 6, 22, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
