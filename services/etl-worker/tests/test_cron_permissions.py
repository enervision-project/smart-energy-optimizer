"""Vérifie que les tâches cron peuvent lire leur environnement et créer leurs verrous."""

import unittest
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parents[1]


class CronPermissionTests(unittest.TestCase):
    def test_runtime_directory_is_owned_by_appuser(self):
        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "install -d -o appuser -g appuser -m 0750 /run/etl-worker",
            dockerfile,
        )
        self.assertIn('CMD ["/usr/local/bin/etl-cron-start"]', dockerfile)
        self.assertNotIn("USER 10001", dockerfile)

    def test_environment_file_is_readable_by_appuser_only(self):
        start_script = (WORKER_DIR / "cron/start.sh").read_text(encoding="utf-8")
        job_script = (WORKER_DIR / "cron/job.sh").read_text(encoding="utf-8")

        self.assertIn(
            'Path("/run/etl-worker/etl-worker.env").write_text(', start_script
        )
        self.assertIn(
            "chown appuser:appuser /run/etl-worker/etl-worker.env", start_script
        )
        self.assertIn("chmod 0640 /run/etl-worker/etl-worker.env", start_script)
        self.assertIn(". /run/etl-worker/etl-worker.env", job_script)

    def test_cron_runs_as_root_and_drops_privileges_for_etl_commands(self):
        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")
        cron_file = (WORKER_DIR / "cron/etl").read_text(encoding="utf-8")
        job_script = (WORKER_DIR / "cron/job.sh").read_text(encoding="utf-8")

        self.assertIn(
            "install -d -o appuser -g appuser -m 0750 /run/etl-worker", dockerfile
        )
        cron_jobs = [
            line
            for line in cron_file.splitlines()
            if "/usr/local/bin/etl-cron-job" in line
        ]
        self.assertTrue(cron_jobs)
        # Seul root peut écrire dans /proc/1/fd/1 et 2 : la redirection cron échoue sous appuser.
        self.assertTrue(
            all(" root /usr/local/bin/etl-cron-job" in line for line in cron_jobs)
        )
        self.assertIn('exec 9>"/run/etl-worker/etl-$1.lock"', job_script)
        self.assertIn(
            "setpriv --reuid=appuser --regid=appuser --init-groups etl-sync-alerts",
            job_script,
        )
        self.assertIn(
            'setpriv --reuid=appuser --regid=appuser --init-groups etl-worker "$1"',
            job_script,
        )


if __name__ == "__main__":
    unittest.main()
