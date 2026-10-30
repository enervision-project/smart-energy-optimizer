import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from etl_worker.extract import alerts_main, extract_alerts

ALERT = {
    "alert_id": "ALR-SITE004-1792566802",
    "timestamp": "2026-10-21T07:06:22.042656",
    "site_id": "SITE004",
    "severity": "critical",
    "type": "outage",
    "message": "Risque de surcharge détecté sur Centre Commercial Lille",
    "value": None,
    "threshold": 270.123456789,
}


def response(payload):
    return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


class ExtractAlertsTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_preserves_all_fields_and_uses_an_unfiltered_get(self, urlopen):
        alerts = [
            ALERT | {"extra": {"tags": ["énergie"], "enabled": False}},
            ALERT
            | {
                "alert_id": "ALR-2",
                "timestamp": "2026-10-21T09:06:22.042656+02:00",
                "value": 19.123456789,
            },
        ]
        urlopen.return_value = response(alerts)

        result = extract_alerts(" http://energy-api.test:8000/// ", timeout=3)

        self.assertEqual(result, alerts)
        urlopen.assert_called_once()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://energy-api.test:8000/api/v1/alerts")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 3})

    @patch.dict(os.environ, {"ENERGY_API_BASE_URL": "http://configured-api.test"})
    @patch("etl_worker.extract.urlopen")
    def test_reads_base_url_from_environment(self, urlopen):
        urlopen.return_value = response([ALERT])

        self.assertEqual(extract_alerts(), [ALERT])

        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            "http://configured-api.test/api/v1/alerts",
        )

    @patch("etl_worker.extract.urlopen")
    def test_empty_list_is_valid(self, urlopen):
        urlopen.return_value = response([])
        self.assertEqual(extract_alerts("http://energy-api.test"), [])

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.extract.urlopen")
    def test_missing_or_blank_configuration_fails_before_request(self, urlopen):
        for base_url in (None, "", "   "):
            with (
                self.subTest(base_url=base_url),
                self.assertRaisesRegex(ValueError, "ENERGY_API_BASE_URL"),
            ):
                extract_alerts(base_url)
        urlopen.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_rejects_unexpected_response_shapes(self, urlopen):
        for payload in (None, {}, {"alerts": []}, [None], ["ALR-1"]):
            with self.subTest(payload=payload):
                urlopen.return_value = response(payload)
                with self.assertRaisesRegex(ValueError, "liste d'objets JSON"):
                    extract_alerts("http://energy-api.test")

    @patch("etl_worker.extract.urlopen")
    def test_missing_required_fields_are_distinct_from_explicit_null(self, urlopen):
        for field in ALERT:
            with self.subTest(field=field):
                incomplete = {
                    key: value for key, value in ALERT.items() if key != field
                }
                urlopen.return_value = response([ALERT, incomplete])
                with self.assertRaisesRegex(ValueError, field):
                    extract_alerts("http://energy-api.test")

        urlopen.return_value = response([ALERT])
        self.assertIsNone(extract_alerts("http://energy-api.test")[0]["value"])

    @patch("etl_worker.extract.urlopen")
    def test_invalid_json_is_not_treated_as_no_alerts(self, urlopen):
        urlopen.return_value = io.BytesIO(b"not json")
        with self.assertRaises(json.JSONDecodeError):
            extract_alerts("http://energy-api.test")

    @patch("etl_worker.extract.urlopen")
    def test_http_network_and_timeout_failures_are_propagated(self, urlopen):
        http_error = HTTPError(
            "http://energy-api.test/api/v1/alerts", 503, "Unavailable", {}, None
        )
        self.addCleanup(http_error.close)
        for error in (
            http_error,
            URLError("Connection refused"),
            TimeoutError("Timeout"),
        ):
            with self.subTest(error=type(error).__name__):
                urlopen.side_effect = error
                with self.assertRaises(type(error)) as caught:
                    extract_alerts("http://energy-api.test")
                self.assertIs(caught.exception, error)

    @patch("sys.argv", ["etl-extract-alerts"])
    @patch.dict(
        os.environ, {"ENERGY_API_BASE_URL": "http://energy-api.test"}, clear=True
    )
    @patch("etl_worker.extract.urlopen")
    def test_command_outputs_json_without_database_configuration(self, urlopen):
        urlopen.return_value = response([ALERT])
        with redirect_stdout(io.StringIO()) as output:
            alerts_main()
        self.assertEqual(json.loads(output.getvalue()), [ALERT])
        self.assertIn("détecté", output.getvalue())

    @patch("sys.argv", ["etl-extract-alerts"])
    @patch(
        "etl_worker.extract.extract_alerts", side_effect=RuntimeError("API unavailable")
    )
    def test_command_propagates_failure_without_success_output(self, extract):
        with (
            redirect_stdout(io.StringIO()) as output,
            self.assertRaisesRegex(RuntimeError, "API unavailable"),
        ):
            alerts_main()
        self.assertEqual(output.getvalue(), "")
