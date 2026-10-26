"""Vérifie l'archivage des réponses originales, sans accès à S3."""

import json
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from etl_worker.bronze import write_readings_bronze

CAPTURED = datetime.fromisoformat("2026-10-26T09:03:15.123456+01:00")
READINGS = [
    {"site_id": "SITE001", "timestamp": "2026-10-26T08:03:16.268687", "consumption_kw": None,
     "null_reasons": ["capteur défaillant"], "data_quality": "critical", "extra": {"value": None}},
    {"site_id": "SITE002", "timestamp": "2026-10-26T08:04:00.998877+00:00", "consumption_kw": 12.56789123},
]


class BronzeTests(unittest.TestCase):
    def test_different_timestamps_and_nulls_are_archived_intact(self):
        client = MagicMock()
        before = deepcopy(READINGS)
        key = write_readings_bronze(READINGS, "lake", client=client, collected_at=CAPTURED)
        self.assertEqual(
            key,
            "bronze/readings/minutes/date=2026-10-26/hour=08/2026-10-26T08-03-15.123456Z.jsonl",
        )
        call = client.put_object.call_args.kwargs
        self.assertEqual((call["Bucket"], call["Key"]), ("lake", key))
        lines = call["Body"].decode("utf-8").splitlines()
        self.assertEqual([json.loads(line) for line in lines], before)
        self.assertEqual(READINGS, before)

    def test_two_captures_of_the_same_minute_have_distinct_keys(self):
        client = MagicMock()
        keys = [
            write_readings_bronze(READINGS, "lake", client=client, collected_at=instant)
            for instant in (CAPTURED, CAPTURED + timedelta(microseconds=1))
        ]
        self.assertNotEqual(*keys)

    @patch("etl_worker.bronze.datetime")
    def test_default_capture_time_is_read_in_utc(self, clock):
        clock.now.return_value = CAPTURED.astimezone(UTC)
        write_readings_bronze(READINGS, "lake", client=MagicMock())
        clock.now.assert_called_once_with(UTC)

    def test_without_bucket_or_readings_nothing_is_written(self):
        client = MagicMock()
        with patch.dict("os.environ", {"BRONZE_BUCKET": ""}):
            self.assertIsNone(write_readings_bronze(READINGS, client=client))
        self.assertIsNone(write_readings_bronze([], "lake", client=client))
        client.put_object.assert_not_called()

    def test_naive_capture_time_fails_before_writing(self):
        client = MagicMock()
        with self.assertRaisesRegex(ValueError, "fuseau"):
            write_readings_bronze(
                READINGS, "lake", client=client, collected_at=CAPTURED.replace(tzinfo=None),
            )
        client.put_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
