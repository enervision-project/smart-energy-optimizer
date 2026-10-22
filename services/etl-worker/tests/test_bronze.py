"""Vérifie l'archivage bronze des mesures sans accès à S3."""

import json
import unittest
from unittest.mock import MagicMock, patch

from etl_worker.bronze import write_readings_bronze

READINGS = [
    {"site_id": "SITE001", "timestamp": "2026-10-21T10:08:00+02:00", "consumption_kw": None},
    {"site_id": "SITE002", "timestamp": "2026-10-21T10:08:00+02:00", "consumption_kw": 12.5},
]


class BronzeTests(unittest.TestCase):
    def test_readings_are_written_unchanged_under_utc_minute_key(self):
        client = MagicMock()

        key = write_readings_bronze(READINGS, "lake", client=client)

        self.assertEqual(
            key, "bronze/readings/minutes/date=2026-10-21/hour=08/2026-10-21T08-08Z.jsonl"
        )
        call = client.put_object.call_args.kwargs
        self.assertEqual((call["Bucket"], call["Key"]), ("lake", key))
        lines = call["Body"].decode("utf-8").splitlines()
        self.assertEqual([json.loads(line) for line in lines], READINGS)

    def test_without_bucket_nothing_is_written(self):
        client = MagicMock()
        with patch.dict("os.environ", {"BRONZE_BUCKET": ""}):
            self.assertIsNone(write_readings_bronze(READINGS, client=client))
        client.put_object.assert_not_called()

    def test_mixed_minutes_are_rejected(self):
            readings = [READINGS[0], {**READINGS[1], "timestamp": "2026-10-21T10:09:00+02:00"}]
            mock_client = MagicMock()
            with self.assertRaisesRegex(ValueError, "même timestamp"):
                write_readings_bronze(readings, "lake", client=mock_client)


if __name__ == "__main__":
    unittest.main()
