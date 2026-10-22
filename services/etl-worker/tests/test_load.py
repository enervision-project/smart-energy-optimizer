"""Tests du chargement des sites.

Les tests PostgreSQL utilisent TEST_DATABASE_URL et un schéma temporaire isolé.
Ils sont ignorés si cette variable n'est pas définie.
"""

import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from etl_worker.load import load_sites, read_site_ids

SITE = {
    "site_id": "SITE001",
    "site_name": "Bureau Paris La Défense",
    "site_type": "office",
    "location": None,
    "capacity_kw": 200.0,
    "status": "active",
}

_SITES_SCHEMA = """
    CREATE TABLE sites (
        site_id TEXT PRIMARY KEY,
        site_name TEXT NOT NULL,
        site_type TEXT NOT NULL,
        location TEXT,
        capacity_kw DOUBLE PRECISION NOT NULL CHECK (capacity_kw > 0),
        status TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""


class LoadSitesConfigurationTests(unittest.TestCase):
    @patch("etl_worker.load.psycopg.connect")
    def test_empty_batch_does_not_open_a_connection(self, mock_connect):
        self.assertEqual(load_sites([]), 0)
        mock_connect.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.load.psycopg.connect")
    def test_missing_configuration_fails_before_connecting(self, mock_connect):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            load_sites([SITE])
        mock_connect.assert_not_called()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured-db/enervision"})
    @patch("etl_worker.load.psycopg.connect")
    def test_reads_configuration_and_propagates_connection_failure(self, mock_connect):
        error = psycopg.OperationalError("Connection refused")
        mock_connect.side_effect = error

        with self.assertRaises(psycopg.OperationalError) as caught:
            load_sites([SITE], connect_timeout=2)

        self.assertIs(caught.exception, error)
        mock_connect.assert_called_once_with(
            "postgresql://configured-db/enervision", connect_timeout=2
        )


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "Définir TEST_DATABASE_URL pour les tests PostgreSQL.",
)
class LoadSitesPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema_name = f"test_sites_{uuid4().hex}"
        self.connection = psycopg.connect(
            base_url, autocommit=True, row_factory=dict_row
        )
        self.addCleanup(self.connection.close)
        self.connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name)),
        )
        self.connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
        )
        self.connection.execute(_SITES_SCHEMA)
        self.database_url = make_conninfo(
            base_url, options=f"-c search_path={schema_name}"
        )

    def stored_sites(self):
        return self.connection.execute(
            "SELECT * FROM sites ORDER BY site_id"
        ).fetchall()

    def test_inserts_new_sites(self):
        sites = [SITE, SITE | {"site_id": "SITE002", "site_name": "Second site"}]

        self.assertEqual(load_sites(sites, self.database_url), 2)

        stored = self.stored_sites()
        self.assertEqual(
            [{key: row[key] for key in SITE} for row in stored], sites
        )
        self.assertTrue(all(row["updated_at"] is not None for row in stored))

    def test_identical_site_keeps_its_updated_at(self):
        load_sites([SITE], self.database_url)
        self.connection.execute(
            "UPDATE sites SET updated_at = %s",
            (datetime(2000, 1, 1, tzinfo=UTC),),
        )
        before = self.stored_sites()

        self.assertEqual(load_sites([SITE], self.database_url), 0)

        self.assertEqual(self.stored_sites(), before)

    def test_each_changed_field_is_updated(self):
        changes = {
            "site_name": "Bureau d'essai",
            "site_type": "factory",
            "location": "Lyon, France",
            "capacity_kw": 250.0,
            "status": "inactive",
        }
        old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
        for field, value in changes.items():
            with self.subTest(field=field):
                load_sites([SITE], self.database_url)
                self.connection.execute(
                    "UPDATE sites SET updated_at = %s", (old_timestamp,)
                )
                modified = SITE | {field: value}

                self.assertEqual(load_sites([modified], self.database_url), 1)

                stored = self.stored_sites()[0]
                self.assertEqual({key: stored[key] for key in SITE}, modified)
                self.assertGreater(stored["updated_at"], old_timestamp)

    def test_location_changes_to_and_from_null(self):
        load_sites([SITE], self.database_url)
        for location in ("Lyon, France", None):
            with self.subTest(location=location):
                modified = SITE | {"location": location}

                self.assertEqual(load_sites([modified], self.database_url), 1)
                self.assertEqual(self.stored_sites()[0]["location"], location)
                self.assertEqual(load_sites([modified], self.database_url), 0)

    def test_mixed_batch_only_changes_the_expected_sites(self):
        second = SITE | {"site_id": "SITE002", "site_name": "Second site"}
        load_sites([SITE, second], self.database_url)
        unchanged = self.stored_sites()[0]
        changed = second | {"status": "inactive"}
        new = SITE | {"site_id": "SITE003", "site_name": "Third site"}

        self.assertEqual(load_sites([SITE, changed, new], self.database_url), 2)

        stored = self.stored_sites()
        self.assertEqual(len(stored), 3)
        self.assertEqual(stored[0], unchanged)
        self.assertEqual(stored[1]["status"], "inactive")
        self.assertEqual(stored[2]["site_id"], "SITE003")

    def test_invalid_site_rolls_back_the_entire_batch(self):
        load_sites([SITE], self.database_url)
        before = self.stored_sites()
        changed = SITE | {"status": "inactive"}
        new = SITE | {"site_id": "SITE002"}
        invalid = SITE | {"site_id": "SITE003", "capacity_kw": -1.0}

        with self.assertRaises(psycopg.errors.CheckViolation):
            load_sites([changed, new, invalid], self.database_url)

        self.assertEqual(self.stored_sites(), before)

    def test_reads_site_ids_from_database_in_stable_order(self):
        load_sites([SITE | {"site_id": "SITE002"}, SITE], self.database_url)

        self.assertEqual(read_site_ids(self.database_url), ["SITE001", "SITE002"])

    def test_read_site_ids_returns_empty_list_for_empty_table(self):
        self.assertEqual(read_site_ids(self.database_url), [])
