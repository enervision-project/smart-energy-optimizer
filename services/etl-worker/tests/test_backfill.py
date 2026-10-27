"""Rattrapage des minutes manquantes, sans réseau ni base."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, call, patch
from urllib.error import URLError
from zoneinfo import ZoneInfo

from etl_worker.backfill import backfill_readings, backfill_window, split_range

NOW = datetime(2026, 10, 26, 10, 1, 30, tzinfo=UTC)
START = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)


class BackfillWindowTests(unittest.TestCase):
    def test_window_stops_before_the_previous_minute(self):
        # À 10:01:30, la dernière minute examinée est 09:59 : 10:00 reste à sync-readings.
        self.assertEqual(
            backfill_window(6, NOW),
            (
                datetime(2026, 10, 26, 4, 0, tzinfo=UTC),
                datetime(2026, 10, 26, 10, 0, tzinfo=UTC),
            ),
        )

    def test_paris_reference_is_converted_to_utc(self):
        paris = NOW.astimezone(
            datetime.fromisoformat("2026-10-26T11:01:30+01:00").tzinfo
        )
        self.assertEqual(backfill_window(1, paris), backfill_window(1, NOW))

    def test_invalid_arguments_are_rejected(self):
        naive_now = NOW.replace(tzinfo=None)
        with self.assertRaises(ValueError):
            backfill_window(0, NOW)
        with self.assertRaises(ValueError):
            backfill_window(1, naive_now)


class SplitRangeTests(unittest.TestCase):
    def test_long_range_is_split_in_chunks_of_1000_minutes(self):
        end = START + timedelta(minutes=2500)
        self.assertEqual(
            split_range(START, end),
            [
                (START, START + timedelta(minutes=1000)),
                (START + timedelta(minutes=1000), START + timedelta(minutes=2000)),
                (START + timedelta(minutes=2000), end),
            ],
        )

    def test_short_range_is_a_single_chunk(self):
        end = START + timedelta(minutes=2)
        self.assertEqual(split_range(START, end), [(START, end)])

    def test_chunks_keep_1000_real_minutes_across_a_time_change(self):
        # Bornes en heure de Paris, comme les renvoie la base ; le 25/10/2026 à 3 h, il est 2 h.
        paris = ZoneInfo("Europe/Paris")
        start = datetime(2026, 10, 25, 1, 0, tzinfo=paris)
        end = datetime(2026, 10, 25, 23, 0, tzinfo=paris)
        chunks = split_range(start, end)
        self.assertTrue(
            all(last - first <= timedelta(minutes=1000) for first, last in chunks)
        )
        self.assertEqual(chunks[0][0], start)
        self.assertEqual(chunks[-1][1], end)
        # 23 heures réelles ce jour-là : end - start, dans le même fuseau, en donnerait 22.
        total = sum((last - first for first, last in chunks), timedelta())
        self.assertEqual(total, timedelta(hours=23))


@patch("etl_worker.backfill.load_readings")
@patch("etl_worker.backfill.write_readings_bronze")
@patch("etl_worker.backfill.extract_history")
@patch("etl_worker.backfill.read_missing_ranges")
class BackfillReadingsTests(unittest.TestCase):
    def test_each_range_is_archived_then_loaded_as_backfill(
        self, ranges, extract, bronze, load
    ):
        ranges.return_value = [
            ("SITE001", START, START + timedelta(minutes=2)),
            ("SITE002", START, START + timedelta(minutes=1)),
        ]
        extract.side_effect = lambda site, start, end, base_url: (
            [{"site_id": site}] * int((end - start) / timedelta(minutes=1))
        )
        load.side_effect = lambda readings, database_url, source: len(readings)

        result = backfill_readings(
            6, now=NOW, base_url="http://api.test", database_url="postgresql://db"
        )

        ranges.assert_called_once_with(
            datetime(2026, 10, 26, 4, 0, tzinfo=UTC),
            datetime(2026, 10, 26, 10, 0, tzinfo=UTC),
            "postgresql://db",
        )
        self.assertEqual(
            (result.ranges, result.received, result.inserted, result.errors),
            (2, 3, 3, {}),
        )
        bronze.assert_has_calls(
            [
                call(ANY, kind="backfill", label="SITE001_20261026T0800-20261026T0802"),
                call(ANY, kind="backfill", label="SITE002_20261026T0800-20261026T0801"),
            ]
        )
        self.assertTrue(
            all(c.kwargs["source"] == "backfill" for c in load.call_args_list)
        )

    def test_failing_chunk_is_reported_without_stopping_the_others(
        self, ranges, extract, bronze, load
    ):
        ranges.return_value = [
            ("SITE001", START, START + timedelta(minutes=1)),
            ("SITE002", START, START + timedelta(minutes=1)),
            ("SITE003", START, START + timedelta(minutes=1)),
        ]
        extract.side_effect = [
            [{"site_id": "SITE001"}],
            URLError("timed out"),
            ValueError("Rattrapage SITE003 : 0 mesures reçues"),
        ]
        load.return_value = 1

        result = backfill_readings(6, now=NOW)

        self.assertEqual((result.ranges, result.received, result.inserted), (3, 1, 1))
        self.assertEqual(
            sorted(result.errors),
            [
                "SITE002_20261026T0800-20261026T0801",
                "SITE003_20261026T0800-20261026T0801",
            ],
        )
        self.assertIn("timed out", result.errors["SITE002_20261026T0800-20261026T0801"])
        bronze.assert_called_once()
        load.assert_called_once()

    def test_no_missing_minute_means_no_api_call(self, ranges, extract, bronze, load):
        ranges.return_value = []

        result = backfill_readings(6, now=NOW)

        self.assertEqual(
            (result.ranges, result.received, result.inserted, result.errors),
            (0, 0, 0, {}),
        )
        extract.assert_not_called()
        bronze.assert_not_called()
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
