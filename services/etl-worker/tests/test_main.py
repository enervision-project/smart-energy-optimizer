"""Vérifie l'initialisation et la collecte planifiées sans réseau."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock
from unittest.mock import ANY, patch

from etl_worker.__main__ import main
from etl_worker.backfill import BackfillResult

PROFILES = [{"site_id": "SITE001"}]


class WorkerCommandTests(unittest.TestCase):
    def setUp(self):
        self.read_ids = self.patch("read_site_ids")
        self.extract_sites = self.patch("extract_sites")
        self.load_sites = self.patch("load_sites")
        self.read_profiles = self.patch("read_site_profiles")
        self.read_profiles.return_value = PROFILES
        self.load_profiles = self.patch("load_site_profiles")
        self.load_profiles.return_value = 0
        self.extract_readings = self.patch("extract_readings")
        self.load_readings = self.patch("load_readings")
        self.write_bronze = self.patch("write_readings_bronze")
        self.write_bronze.return_value = None
        self.aggregate_hour = self.patch("aggregate_hour")
        self.impute = self.patch("impute_consumption")
        self.impute.return_value = 0

    def patch(self, name):
        patcher = patch(f"etl_worker.__main__.{name}")
        self.addCleanup(patcher.stop)
        return patcher.start()

    def run_command_with(self, *arguments):
        with (
            patch("sys.argv", ["etl-worker", *arguments]),
            redirect_stdout(io.StringIO()) as output,
        ):
            main()
        return output.getvalue()

    def run_command(self, command):
        with (
            patch("sys.argv", ["etl-worker", command]),
            redirect_stdout(io.StringIO()) as output,
        ):
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

    def test_site_commands_do_not_touch_profiles(self):
        self.extract_sites.return_value = [{"site_id": "SITE001"}]
        for command, existing_ids in (
            ("init-sites", []),
            ("init-sites", ["SITE001"]),
            ("sync-sites", []),
        ):
            with self.subTest(command=command, existing_ids=existing_ids):
                self.read_ids.return_value = existing_ids

                self.run_command(command)

                self.read_profiles.assert_not_called()
                self.load_profiles.assert_not_called()

    def test_profile_command_loads_shipped_file_without_sites_api(self):
        self.load_profiles.return_value = 1

        output = self.run_command("sync-site-profiles")

        self.read_profiles.assert_called_once_with()
        self.load_profiles.assert_called_once_with(PROFILES)
        self.read_ids.assert_not_called()
        self.extract_sites.assert_not_called()
        self.load_sites.assert_not_called()
        self.assertIn("Profils de référence : 1 ; insérés ou mis à jour : 1", output)

    def test_profile_command_fails_visibly(self):
        self.load_profiles.side_effect = RuntimeError("check violation")

        with self.assertRaisesRegex(RuntimeError, "check violation"):
            self.run_command("sync-site-profiles")

    def test_readings_use_database_sites_without_sites_api(self):
        self.read_ids.return_value = ["SITE001", "SITE002"]
        readings = [{"site_id": "SITE001"}, {"site_id": "SITE002"}]
        self.extract_readings.return_value = (readings, {})
        self.load_readings.return_value = 1

        output = self.run_command("sync-readings")

        self.extract_sites.assert_not_called()
        self.extract_readings.assert_called_once_with(["SITE001", "SITE002"])
        self.load_readings.assert_called_once_with(readings, source="current")
        self.load_profiles.assert_not_called()
        self.assertIn(
            "Mesures reçues : 2/2 ; insérées : 1 ; déjà présentes : 1", output
        )

    def test_collection_imputes_the_last_fifteen_minutes(self):
        self.read_ids.return_value = ["SITE001"]
        self.extract_readings.return_value = ([{"site_id": "SITE001"}], {})
        self.load_readings.return_value = 1
        self.impute.return_value = 3

        output = self.run_command("sync-readings")

        self.impute.assert_called_once_with(minutes=15)
        self.assertIn("Consommations imputées : 3.", output)

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_failing_sites_do_not_block_the_others_but_fail_the_job(self, mock_stderr):
        self.read_ids.return_value = ["SITE001", "SITE002", "SITE003"]
        readings = [{"site_id": "SITE001"}, {"site_id": "SITE003"}]
        self.extract_readings.return_value = (
            readings,
            {"SITE002": "HTTP Error 503: Service Unavailable"},
        )
        self.load_readings.return_value = 2

        with self.assertRaises(SystemExit) as caught:
            self.run_command("sync-readings")

        self.assertEqual(caught.exception.code, 1)
        self.write_bronze.assert_called_once_with(readings, collected_at=ANY)
        self.load_readings.assert_called_once_with(readings, source="current")
        self.assertIn("SITE002 : HTTP Error 503", mock_stderr.getvalue())

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_all_sites_failing_writes_nothing(self, _mock_stderr):
        self.read_ids.return_value = ["SITE001"]
        self.extract_readings.return_value = ([], {"SITE001": "timed out"})

        with self.assertRaises(SystemExit) as caught:
            self.run_command("sync-readings")

        self.assertEqual(caught.exception.code, 1)
        self.write_bronze.assert_not_called()
        self.load_readings.assert_not_called()
        self.impute.assert_not_called()

    def test_readings_are_archived_in_bronze_before_loading(self):
        self.read_ids.return_value = ["SITE001"]
        readings = [{"site_id": "SITE001"}]
        self.extract_readings.return_value = (readings, {})
        self.load_readings.return_value = 1
        key = "bronze/readings/minutes/date=2026-10-21/hour=08/2026-10-21T08-08Z.jsonl"
        self.write_bronze.return_value = key

        output = self.run_command("sync-readings")

        self.write_bronze.assert_called_once_with(readings, collected_at=ANY)
        self.assertIn(key, output)

    def test_bronze_failure_skips_database_load(self):
        self.read_ids.return_value = ["SITE001"]
        self.extract_readings.return_value = ([{"site_id": "SITE001"}], {})
        self.write_bronze.side_effect = RuntimeError("s3 unavailable")

        with self.assertRaisesRegex(RuntimeError, "s3 unavailable"):
            self.run_command("sync-readings")

        self.load_readings.assert_not_called()

    def test_extract_still_outputs_json_without_loading(self):
        self.read_ids.return_value = ["SITE001"]
        readings = [{"site_id": "SITE001", "consumption_kw": None}]
        self.extract_readings.return_value = (readings, {})

        self.assertEqual(json.loads(self.run_command("extract-readings")), readings)

        self.load_readings.assert_not_called()
        self.write_bronze.assert_not_called()
        self.extract_sites.assert_not_called()

    def test_collecting_without_sites_fails_visibly(self):
        self.read_ids.return_value = []

        with self.assertRaisesRegex(ValueError, "sync-sites"):
            self.run_command("sync-readings")

        self.extract_readings.assert_not_called()
        self.load_readings.assert_not_called()

    def test_hourly_command_uses_only_database_aggregation(self):
        self.aggregate_hour.return_value = 7

        output = self.run_command("sync-hours")

        self.aggregate_hour.assert_called_once_with(end_time=None, hours=6)
        self.read_ids.assert_not_called()
        self.extract_sites.assert_not_called()
        self.extract_readings.assert_not_called()
        self.load_readings.assert_not_called()
        self.assertIn("readings_hours : 7", output)

    def test_hourly_command_accepts_an_explicit_reference_for_replay(self):
        self.aggregate_hour.return_value = 1
        reference = "2026-10-20T14:00:00+02:00"
        with (
            patch("sys.argv", ["etl-worker", "sync-hours", "--end-time", reference]),
            redirect_stdout(io.StringIO()),
        ):
            main()

        self.assertEqual(
            self.aggregate_hour.call_args.kwargs["end_time"].isoformat(), reference
        )

    def test_hourly_command_can_recalculate_several_hours(self):
        self.aggregate_hour.return_value = 42

        output = self.run_command_with("sync-hours", "--hours", "6")

        self.aggregate_hour.assert_called_once_with(end_time=None, hours=6)
        self.assertIn("readings_hours : 42", output)

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_hours_must_be_positive_and_reserved_to_hourly_command(self, _mock_stderr):
        for arguments in (
            ["sync-hours", "--hours", "0"],
            ["backfill-readings", "--hours", "-1"],
            ["sync-readings", "--hours", "6"],
        ):
            with (
                self.subTest(arguments=arguments),
                patch("sys.argv", ["etl-worker", *arguments]),
                self.assertRaises(SystemExit) as caught,
            ):
                main()
            self.assertEqual(caught.exception.code, 2)
        self.aggregate_hour.assert_not_called()

    def test_backfill_command_reports_its_result(self):
        with patch("etl_worker.__main__.backfill_readings") as backfill:
            backfill.return_value = BackfillResult(ranges=2, received=61, inserted=61)
            output = self.run_command_with("backfill-readings", "--hours", "168")

        backfill.assert_called_once_with(168)
        self.impute.assert_called_once_with(minutes=168 * 60)
        self.assertIn(
            "Plages manquantes : 2 ; mesures rattrapées : 61 ; insérées : 61.", output
        )

    @mock.patch("etl_worker.__main__.backfill_readings")
    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_backfill_defaults_to_six_hours_and_fails_on_errors(
        self, mock_stderr, backfill
    ):
        backfill.return_value = BackfillResult(
            ranges=1, errors={"SITE001_x": "timed out"}
        )
        with self.assertRaises(SystemExit) as caught:
            self.run_command("backfill-readings")

        backfill.assert_called_once_with(6)
        self.impute.assert_called_once_with(minutes=360)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("SITE001_x : timed out", mock_stderr.getvalue())

    def test_impute_command_covers_six_hours_by_default(self):
        self.impute.return_value = 12

        output = self.run_command("impute-readings")

        self.impute.assert_called_once_with(minutes=360)
        self.assertIn("Consommations imputées : 12.", output)
        self.extract_readings.assert_not_called()

    def test_impute_command_can_catch_up_a_week(self):
        self.run_command_with("impute-readings", "--hours", "168")

        self.impute.assert_called_once_with(minutes=168 * 60)

    @mock.patch(
        "sys.argv",
        [
            "etl-worker",
            "sync-readings",
            "--end-time",
            "2026-10-20T14:00:00+02:00",
        ],
    )
    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_end_time_cannot_silently_apply_to_a_raw_command(self, _mock_stderr):
        with self.assertRaises(SystemExit) as caught:
            main()

        self.assertEqual(caught.exception.code, 2)
        self.extract_readings.assert_not_called()
