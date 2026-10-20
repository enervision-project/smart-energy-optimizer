"""Vérifie l'initialisation et la collecte planifiées sans réseau."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from etl_worker.__main__ import main


class WorkerCommandTests(unittest.TestCase):
    def setUp(self):
        self.read_ids = self.patch("read_site_ids")
        self.extract_sites = self.patch("extract_sites")
        self.load_sites = self.patch("load_sites")
        self.extract_readings = self.patch("extract_readings")
        self.load_readings = self.patch("load_readings")

    def patch(self, name):
        patcher = patch(f"etl_worker.__main__.{name}")
        self.addCleanup(patcher.stop)
        return patcher.start()

    def run_command(self, command):
        with patch("sys.argv", ["etl-worker", command]), redirect_stdout(io.StringIO()) as output:
            main()
        return output.getvalue()

    def test_initial_start_populates_empty_sites_table(self):
        self.read_ids.return_value = []
        sites = [{"site_id": "SITE001"}]
        self.extract_sites.return_value = sites
        self.load_sites.return_value = 1

        self.run_command("init-sites")

        self.extract_sites.assert_called_once_with()
        self.load_sites.assert_called_once_with(sites)

    def test_restart_does_not_refresh_existing_sites(self):
        self.read_ids.return_value = ["SITE001"]

        self.run_command("init-sites")

        self.extract_sites.assert_not_called()
        self.load_sites.assert_not_called()

    def test_empty_api_cannot_complete_initialization(self):
        self.read_ids.return_value = []
        self.extract_sites.return_value = []

        with self.assertRaisesRegex(ValueError, "Aucun site reçu"):
            self.run_command("init-sites")

        self.load_sites.assert_not_called()

    def test_database_failure_aborts_initialization(self):
        self.read_ids.side_effect = RuntimeError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.run_command("init-sites")

        self.extract_sites.assert_not_called()

    def test_daily_sync_always_refreshes_sites(self):
        sites = [{"site_id": "SITE001"}]
        self.extract_sites.return_value = sites
        self.load_sites.return_value = 0

        self.run_command("sync-sites")

        self.read_ids.assert_not_called()
        self.extract_sites.assert_called_once_with()
        self.load_sites.assert_called_once_with(sites)

    def test_readings_use_database_sites_without_sites_api(self):
        self.read_ids.return_value = ["SITE001", "SITE002"]
        readings = [{"site_id": "SITE001"}, {"site_id": "SITE002"}]
        self.extract_readings.return_value = readings
        self.load_readings.return_value = 1

        output = self.run_command("sync-readings")

        self.extract_sites.assert_not_called()
        self.extract_readings.assert_called_once_with(["SITE001", "SITE002"])
        self.load_readings.assert_called_once_with(readings)
        self.assertIn("insérées : 1 ; déjà présentes : 1", output)

    def test_extract_still_outputs_json_without_loading(self):
        self.read_ids.return_value = ["SITE001"]
        readings = [{"site_id": "SITE001", "consumption_kw": None}]
        self.extract_readings.return_value = readings

        self.assertEqual(json.loads(self.run_command("extract-readings")), readings)

        self.load_readings.assert_not_called()
        self.extract_sites.assert_not_called()

    def test_collecting_without_sites_fails_visibly(self):
        self.read_ids.return_value = []

        with self.assertRaisesRegex(ValueError, "sync-sites"):
            self.run_command("sync-readings")

        self.extract_readings.assert_not_called()
        self.load_readings.assert_not_called()
