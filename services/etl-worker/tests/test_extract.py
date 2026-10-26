"""Tests de l'extraction /current, sans accès réseau."""

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlsplit

from etl_worker.extract import extract_readings


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def reading(site_id, timestamp="2026-10-26T08:03:16.268687", **extra):
    return {"site_id": site_id, "timestamp": timestamp, **extra}


class ExtractReadingsTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_empty_site_list_does_not_call_the_api(self, request):
        self.assertEqual(extract_readings([], "http://energy-api.test"), [])
        request.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_fetches_current_objects_without_modifying_precision_or_nulls(self, request):
        readings = [
            reading("SITE001", consumption_kw=None, null_reasons=["capteur défaillant"], extra={"value": None}),
            reading("SITE002", "2026-10-26T08:03:17.123456", consumption_kw=1.234567891),
        ]
        request.side_effect = [response(item) for item in readings]

        result = extract_readings(["SITE001", "SITE002"], " http://energy-api.test/ ", timeout=4)

        self.assertEqual(result, readings)
        for call, site_id in zip(request.call_args_list, ["SITE001", "SITE002"]):
            url = urlsplit(call.args[0].full_url)
            self.assertEqual(url.path, f"/api/v1/sites/{site_id}/current")
            self.assertEqual(url.query, "")
            self.assertEqual(call.kwargs, {"timeout": 4})

    @patch("etl_worker.extract.urlopen")
    def test_timezone_and_fractional_timestamp_are_kept_as_received(self, request):
        payload = reading("SITE001", "2026-10-26T09:03:16.123456+01:00")
        request.return_value = response(payload)
        self.assertEqual(extract_readings(["SITE001"], "http://api.test"), [payload])

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
            with self.subTest(base_url=base_url), self.assertRaisesRegex(ValueError, "ENERGY_API_BASE_URL"):
                extract_readings(["SITE001"], base_url)
        request.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_rejects_invalid_payloads(self, request):
        cases = {
            "Un objet": [None, [], [reading("SITE001")], "SITE001"],
            "ne correspond pas": [{}, reading("SITE002")],
            "Timestamp invalide": [reading("SITE001", None), reading("SITE001", "not a date")],
        }
        for message, payloads in cases.items():
            for payload in payloads:
                with self.subTest(payload=payload):
                    request.return_value = response(payload)
                    with self.assertRaisesRegex(ValueError, message):
                        extract_readings(["SITE001"], "http://api.test")

    @patch("etl_worker.extract.urlopen")
    def test_http_failure_is_not_replaced_by_a_null_measurement(self, request):
        request.side_effect = [response(reading("SITE001")), URLError("unavailable")]
        with self.assertRaises(URLError):
            extract_readings(["SITE001", "SITE002"], "http://api.test")


if __name__ == "__main__":
    unittest.main()
