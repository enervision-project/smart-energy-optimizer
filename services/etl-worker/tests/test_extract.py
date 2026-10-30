import io
import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from etl_worker.extract import extract_history, extract_readings


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def reading(site_id, timestamp="2026-10-26T08:03:16.268687", **extra):
    return {"site_id": site_id, "timestamp": timestamp, **extra}


class ExtractReadingsTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_empty_site_list_does_not_call_the_api(self, request):
        self.assertEqual(extract_readings([], "http://energy-api.test"), ([], {}))
        request.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_fetches_current_objects_without_modifying_precision_or_nulls(
        self, request
    ):
        readings = [
            reading(
                "SITE001",
                consumption_kw=None,
                null_reasons=["capteur défaillant"],
                extra={"value": None},
            ),
            reading(
                "SITE002", "2026-10-26T08:03:17.123456", consumption_kw=1.234567891
            ),
        ]
        request.side_effect = [response(item) for item in readings]

        result = extract_readings(
            ["SITE001", "SITE002"], " http://energy-api.test/ ", timeout=4
        )

        self.assertEqual(result, (readings, {}))
        for call, site_id in zip(request.call_args_list, ["SITE001", "SITE002"]):
            url = urlsplit(call.args[0].full_url)
            self.assertEqual(url.path, f"/api/v1/sites/{site_id}/current")
            self.assertEqual(url.query, "")
            self.assertEqual(call.kwargs, {"timeout": 4})

    @patch("etl_worker.extract.urlopen")
    def test_timezone_and_fractional_timestamp_are_kept_as_received(self, request):
        payload = reading("SITE001", "2026-10-26T09:03:16.123456+01:00")
        request.return_value = response(payload)
        self.assertEqual(
            extract_readings(["SITE001"], "http://api.test"), ([payload], {})
        )

    @patch.dict(os.environ, {"ENERGY_API_BASE_URL": "http://configured-api.test"})
    @patch("etl_worker.extract.urlopen")
    def test_uses_environment_url(self, request):
        request.return_value = response(reading("SITE001"))
        extract_readings(["SITE001"])
        self.assertEqual(
            request.call_args.args[0].full_url,
            "http://configured-api.test/api/v1/sites/SITE001/current",
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.extract.urlopen")
    def test_missing_configuration_fails_before_request(self, request):
        for base_url in (None, "", "   "):
            with (
                self.subTest(base_url=base_url),
                self.assertRaisesRegex(ValueError, "ENERGY_API_BASE_URL"),
            ):
                extract_readings(["SITE001"], base_url)
        request.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_invalid_payloads_are_reported_for_their_site(self, request):
        cases = {
            "Un objet": [None, [], [reading("SITE001")], "SITE001"],
            "ne correspond pas": [{}, reading("SITE002")],
            "Timestamp invalide": [
                reading("SITE001", None),
                reading("SITE001", "not a date"),
            ],
        }
        for message, payloads in cases.items():
            for payload in payloads:
                with self.subTest(payload=payload):
                    request.return_value = response(payload)
                    readings, errors = extract_readings(["SITE001"], "http://api.test")
                    self.assertEqual(readings, [])
                    self.assertIn(message, errors["SITE001"])

    @patch("etl_worker.extract.urlopen")
    def test_invalid_json_is_reported_for_its_site(self, request):
        request.return_value = io.BytesIO(b"<html>")
        readings, errors = extract_readings(["SITE001"], "http://api.test")
        self.assertEqual(readings, [])
        self.assertIn("SITE001", errors)

    @patch("etl_worker.extract.urlopen")
    def test_failing_site_does_not_block_the_others(self, request):
        request.side_effect = [
            response(reading("SITE001")),
            HTTPError("http://api.test", 503, "Service Unavailable", None, None),
            URLError("timed out"),
            response(reading("SITE004")),
        ]

        readings, errors = extract_readings(
            ["SITE001", "SITE002", "SITE003", "SITE004"],
            "http://api.test",
        )

        # A failed site is never replaced by an invented NULL reading.
        self.assertEqual([item["site_id"] for item in readings], ["SITE001", "SITE004"])
        self.assertEqual(list(errors), ["SITE002", "SITE003"])
        self.assertIn("503", errors["SITE002"])
        self.assertIn("timed out", errors["SITE003"])


START = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)


def history(minutes, site_id="SITE001", start=START):
    return [
        reading(
            site_id, (start + timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        for offset in minutes
    ]


class ExtractHistoryTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_requests_one_reading_per_minute_of_the_range(self, request):
        payload = history(range(3))
        request.return_value = response(payload)

        result = extract_history(
            "SITE001", START, START + timedelta(minutes=3), "http://api.test", timeout=5
        )

        self.assertEqual(result, payload)
        url = urlsplit(request.call_args.args[0].full_url)
        self.assertEqual(url.path, "/api/v1/readings")
        self.assertEqual(
            parse_qs(url.query),
            {
                "site_id": ["SITE001"],
                "start_time": ["2026-10-26T08:00:00+00:00"],
                "end_time": ["2026-10-26T08:03:00+00:00"],
                "limit": ["3"],
            },
        )
        self.assertEqual(request.call_args.kwargs, {"timeout": 5})

    @patch("etl_worker.extract.urlopen")
    def test_incomplete_or_misaligned_answers_are_rejected(self, request):
        cases = {
            "manque une minute": history([0, 2]),
            "minute en double": history([0, 0, 1]),
            "minute hors plage": history([0, 1, 3]),
            "autre site": history(range(3), site_id="SITE002"),
        }
        end = START + timedelta(minutes=3)
        for name, payload in cases.items():
            request.return_value = response(payload)
            with self.subTest(name), self.assertRaises(ValueError):
                extract_history("SITE001", START, end, "http://api.test")

    @patch("etl_worker.extract.urlopen")
    def test_non_list_answer_is_rejected(self, request):
        request.return_value = response({"detail": "erreur"})
        end = START + timedelta(minutes=1)
        with self.assertRaises(TypeError):
            extract_history("SITE001", START, end, "http://api.test")

    @patch("etl_worker.extract.urlopen")
    def test_invalid_bounds_fail_before_request(self, request):
        cases = [
            (
                START.replace(tzinfo=None),
                START.replace(tzinfo=None) + timedelta(minutes=1),
            ),
            (START + timedelta(seconds=30), START + timedelta(minutes=2)),
            (START, START),
            (START, START + timedelta(minutes=1001)),
        ]
        for start, end in cases:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                extract_history("SITE001", start, end, "http://api.test")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
