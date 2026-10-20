"""Tests de l'extraction des sites, sans accès réseau."""

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from etl_worker.extract import extract_sites


class ExtractSitesTests(unittest.TestCase):
    @patch("etl_worker.extract.urlopen")
    def test_preserves_all_fields_and_configures_request(self, mock_urlopen):
        sites = [
            {
                "site_id": "SITE001",
                "site_name": "Bureau Paris La Défense",
                "site_type": "office",
                "location": None,
                "capacity_kw": 200.0,
                "status": "active",
                "extra": {"tags": ["test"], "enabled": False},
            }
        ]
        mock_urlopen.return_value = io.BytesIO(json.dumps(sites).encode("utf-8"))

        result = extract_sites("http://energy-api.test:8000/", timeout=3.0)

        self.assertEqual(result, sites)
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://energy-api.test:8000/api/v1/sites")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(mock_urlopen.call_args.kwargs, {"timeout": 3.0})

    @patch.dict(os.environ, {"ENERGY_API_BASE_URL": "http://configured-api.test"})
    @patch("etl_worker.extract.urlopen")
    def test_reads_base_url_from_environment(self, mock_urlopen):
        mock_urlopen.return_value = io.BytesIO(b"[]")

        self.assertEqual(extract_sites(), [])

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://configured-api.test/api/v1/sites")

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.extract.urlopen")
    def test_missing_configuration_fails_before_request(self, mock_urlopen):
        with self.assertRaisesRegex(ValueError, "ENERGY_API_BASE_URL"):
            extract_sites()

        mock_urlopen.assert_not_called()

    @patch("etl_worker.extract.urlopen")
    def test_rejects_unexpected_response_shapes(self, mock_urlopen):
        for payload in ({"sites": []}, [None], ["SITE001"]):
            with self.subTest(payload=payload):
                mock_urlopen.return_value = io.BytesIO(json.dumps(payload).encode())

                with self.assertRaisesRegex(ValueError, "liste d'objets JSON"):
                    extract_sites("http://energy-api.test")

    @patch("etl_worker.extract.urlopen")
    def test_invalid_json_is_not_treated_as_an_empty_list(self, mock_urlopen):
        mock_urlopen.return_value = io.BytesIO(b"not json")

        with self.assertRaises(json.JSONDecodeError):
            extract_sites("http://energy-api.test")

    @patch("etl_worker.extract.urlopen")
    def test_request_failures_are_propagated(self, mock_urlopen):
        http_error = HTTPError(
            "http://energy-api.test", 503, "Service unavailable", {}, None
        )
        self.addCleanup(http_error.close)
        errors = (
            http_error,
            URLError("Connection refused"),
            TimeoutError("Request timed out"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                mock_urlopen.side_effect = error

                with self.assertRaises(type(error)) as caught:
                    extract_sites("http://energy-api.test")

                self.assertIs(caught.exception, error)
