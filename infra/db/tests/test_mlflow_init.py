"""MLflow's privileged initializer must isolate both new and existing databases."""

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]


class MlflowDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.driver = MagicMock()
        self.settings = MagicMock()
        self.settings.database_settings.return_value = {
            "dbname": "mlflow_test",
            "user": "mlflow",
            "password": "isolated-test",
            "host": "db",
            "port": 5432,
        }
        # Driver and settings are supplied at import time; no SQL or MLflow server
        # is contacted by these initializer orchestration tests.
        with patch.dict(
            "sys.modules", {"psycopg2": self.driver, "settings": self.settings}
        ):
            spec = importlib.util.spec_from_file_location(
                "mlflow_init_test", ROOT / "services/ml-service/mlflow/init_db.py"
            )
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.cursor = (
            self.driver.connect.return_value.cursor.return_value.__enter__.return_value
        )
        self.environment = patch.dict(
            os.environ,
            {
                "POSTGRES_DB": "application_test",
                "POSTGRES_USER": "admin_test",
                "POSTGRES_PASSWORD": "isolated-admin-test",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.upgrade = patch.object(self.module.subprocess, "run")
        self.run = self.upgrade.start()
        self.run.return_value.returncode = 0
        self.addCleanup(self.upgrade.stop)

    def templates(self):
        return [call.args[0] for call in self.driver.sql.SQL.call_args_list]

    def test_new_database_has_restricted_account_and_no_public_access(self):
        self.cursor.fetchone.side_effect = [None, None]
        self.assertEqual(self.module.main(), 0)
        templates = self.templates()
        self.assertTrue(
            any("NOSUPERUSER NOCREATEDB NOCREATEROLE" in sql for sql in templates)
        )
        self.assertIn("CREATE DATABASE {} OWNER {}", templates)
        self.assertIn("REVOKE ALL ON DATABASE {} FROM PUBLIC", templates)
        self.run.assert_called_once_with(
            ["mlflow", "db", "upgrade", self.settings.backend_uri.return_value],
            check=False,
        )

    def test_existing_database_also_loses_public_access(self):
        self.cursor.fetchone.side_effect = [("mlflow",), (1,)]
        self.assertEqual(self.module.main(), 0)
        self.assertEqual(self.templates(), ["REVOKE ALL ON DATABASE {} FROM PUBLIC"])

    def test_wrong_owner_is_rejected_before_changes(self):
        self.cursor.fetchone.return_value = ("unexpected_owner",)
        with self.assertRaisesRegex(ValueError, "autre proprietaire"):
            self.module.main()
        self.assertFalse(self.templates())
        self.run.assert_not_called()

    def test_application_database_and_admin_account_cannot_be_reused(self):
        original = self.settings.database_settings.return_value.copy()
        for key, value in [("dbname", "application_test"), ("user", "admin_test")]:
            with self.subTest(key=key):
                settings = original.copy()
                settings[key] = value
                self.settings.database_settings.return_value = settings
                with self.assertRaises(ValueError):
                    self.module.main()
                self.driver.connect.assert_not_called()
                self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
