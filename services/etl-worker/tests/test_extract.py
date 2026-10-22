"""Tests de l'extraction des mesures, sans accès réseau."""

import io
import json
import os
import unittest
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from etl_worker.extract import extract_readings

END_TIME = datetime(2026, 10, 21, 8, 9, 42, 123456, tzinfo=UTC)
WINDOW_START = "2026-10-21T08:08:00+00:00"


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def reading(site_id, timestamp=WINDOW_START, **extra):
    return {"site_id": site_id, "timestamp": timestamp, **extra}


class ExtractReadingsTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_empty_site_list_does_not_call_the_api(self, mock_urlopen):
        self.assertEqual(extract_readings([], "http://energy-api.test"), [])
        mock_urlopen.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_returns_one_reading_per_site_for_the_same_window(self, mock_urlopen):
        readings = [reading("SITE001", consumption_kw=None), reading("SITE002", consumption_kw=1.5)]
        mock_urlopen.side_effect = [response([item]) for item in readings]

        result = extract_readings(
            ["SITE001", "SITE002"], " http://energy-api.test/ ", end_time=END_TIME, timeout=4
        )

        self.assertEqual(result, readings)
        for call, site_id in zip(mock_urlopen.call_args_list, ["SITE001", "SITE002"]):
            url = urlsplit(call.args[0].full_url)
            self.assertEqual(url.path, "/api/v1/readings")
            self.assertEqual(
                parse_qs(url.query),
                {
                    "site_id": [site_id],
                    "start_time": [WINDOW_START],
                    "end_time": ["2026-10-21T08:09:00+00:00"],
                    "limit": ["1"],
                },
            )
            self.assertEqual(call.kwargs, {"timeout": 4})

    @patch("etl_worker.extract.urlopen")
    def test_end_time_in_another_timezone_is_converted_to_utc(self, mock_urlopen):
        mock_urlopen.return_value = response([reading("SITE001", "2026-10-21T10:08:00+02:00")])
        paris = timezone(timedelta(hours=2))

        result = extract_readings(
            ["SITE001"], "http://energy-api.test", end_time=END_TIME.astimezone(paris)
        )

        self.assertEqual(result[0]["timestamp"], "2026-10-21T10:08:00+02:00")

    @patch.dict(os.environ, {"ENERGY_API_BASE_URL": "http://configured-api.test"})
    @patch("etl_worker.extract.datetime")
    @patch("etl_worker.extract.urlopen")
    def test_defaults_to_environment_url_and_current_time(self, mock_urlopen, mock_datetime):
        mock_datetime.now.return_value = END_TIME
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_urlopen.return_value = response([reading("SITE001")])

        extract_readings(["SITE001"])

        mock_datetime.now.assert_called_once_with(UTC)
        self.assertTrue(
            mock_urlopen.call_args.args[0].full_url.startswith(
                "http://configured-api.test/api/v1/readings?"
            )
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.extract.urlopen")
    def test_missing_configuration_fails_before_request(self, mock_urlopen):
        for base_url in (None, "", "   "):
            with self.subTest(base_url=base_url), self.assertRaisesRegex(
                ValueError, "ENERGY_API_BASE_URL"
            ):
                extract_readings(["SITE001"], base_url, end_time=END_TIME)
        mock_urlopen.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_naive_end_time_is_rejected_before_request(self, mock_urlopen):
        naive_end_time = datetime(2026, 10, 21, 8, 9)

        with self.assertRaisesRegex(ValueError, "fuseau horaire"):
            extract_readings(
                ["SITE001"], "http://energy-api.test", end_time=naive_end_time
            )

        mock_urlopen.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_rejects_invalid_payloads(self, mock_urlopen):
        cases = {
            "Une seule mesure": [None, {}, [], [reading("SITE001")] * 2, ["SITE001"]],
            "ne correspond pas": [[reading("SITE002")]],
            "Timestamp invalide": [
                [reading("SITE001", None)],
                [reading("SITE001", "not a date")],
            ],
            "Timestamp inattendu": [
                [reading("SITE001", "2026-10-21T08:08:00")],
                [reading("SITE001", "2026-10-21T08:07:00+00:00")],
            ],
        }
        for message, payloads in cases.items():
            for payload in payloads:
                with self.subTest(payload=payload):
                    mock_urlopen.return_value = response(payload)
                    with self.assertRaisesRegex(ValueError, message):
                        extract_readings(
                            ["SITE001"], "http://energy-api.test", end_time=END_TIME
                        )


if __name__ == "__main__":
    unittest.main()
