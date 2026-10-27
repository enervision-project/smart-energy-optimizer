"""Tests du chargement des profils de référence des sites.

Les tests PostgreSQL utilisent TEST_DATABASE_URL et un schéma temporaire isolé.
Ils sont ignorés si cette variable n'est pas définie.
"""

import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from etl_worker.extract import read_site_profiles
from etl_worker.load import _site_profile_row, load_site_profiles

# Format source : jours 0 = lundi, working_hours [début, fin].
PROFILE = {
    "site_id": "SITE001",
    "base_consumption": 50,
    "peak_consumption": 150,
    "working_hours": [8, 19],
    "working_days": [0, 1, 2, 3, 4],
    "seasonal_variation": 0.3,
    "noise_level": 0.05,
}

# Copie des tables utiles du changeset Liquibase 004 (contraintes comprises).
_SCHEMA = """
    CREATE TABLE sites (site_id TEXT PRIMARY KEY);
    CREATE TABLE site_profiles (
        site_id             TEXT PRIMARY KEY REFERENCES sites (site_id) ON DELETE CASCADE,
        base_consumption    NUMERIC(14, 2) NOT NULL CHECK (base_consumption >= 0),
        peak_consumption    NUMERIC(14, 2) NOT NULL,
        working_hour_start  SMALLINT NOT NULL CHECK (working_hour_start BETWEEN 0 AND 23),
        working_hour_end    SMALLINT NOT NULL CHECK (working_hour_end BETWEEN 1 AND 24),
        working_days        SMALLINT[] NOT NULL
            CHECK (working_days <@ '{1,2,3,4,5,6,7}'::SMALLINT[] AND cardinality(working_days) > 0),
        seasonal_variation  NUMERIC(5, 4) CHECK (seasonal_variation >= 0),
        noise_level         NUMERIC(5, 4) CHECK (noise_level >= 0),
        weekend_factor      NUMERIC(5, 4) CHECK (weekend_factor > 0),
        shift_pattern       BOOLEAN NOT NULL DEFAULT false,
        CHECK (peak_consumption >= base_consumption),
        CHECK (working_hour_start < working_hour_end)
    );
"""


class SiteProfileConversionTests(unittest.TestCase):
    def test_days_are_shifted_to_iso_numbering(self):
        row = _site_profile_row(PROFILE | {"working_days": [0, 1, 2, 3, 4, 5, 6]})

        self.assertEqual(row[5], [1, 2, 3, 4, 5, 6, 7])

    def test_working_hours_are_split_into_start_and_end(self):
        row = _site_profile_row(PROFILE | {"working_hours": [0, 24]})

        self.assertEqual(row[3:5], (0, 24))

    def test_missing_optional_fields_get_defaults(self):
        row = _site_profile_row(PROFILE)

        self.assertIsNone(row[8])  # weekend_factor
        self.assertIs(row[9], False)  # shift_pattern

    def test_optional_fields_are_kept_when_present(self):
        row = _site_profile_row(
            PROFILE | {"weekend_factor": 1.2, "shift_pattern": True}
        )

        self.assertEqual(row[8], 1.2)
        self.assertIs(row[9], True)

    def test_working_hours_must_be_a_pair(self):
        with self.assertRaises(ValueError):
            _site_profile_row(PROFILE | {"working_hours": [8]})


class ShippedSiteProfilesTests(unittest.TestCase):
    def test_file_contains_one_profile_per_dataset_site(self):
        profiles = read_site_profiles()

        self.assertEqual(
            [profile["site_id"] for profile in profiles],
            [f"SITE00{number}" for number in range(1, 8)],
        )

    def test_every_profile_converts(self):
        for profile in read_site_profiles():
            with self.subTest(site_id=profile["site_id"]):
                row = _site_profile_row(profile)
                self.assertLessEqual(set(row[5]), set(range(1, 8)))


class LoadSiteProfilesConfigurationTests(unittest.TestCase):
    @patch("etl_worker.load.psycopg.connect")
    def test_empty_batch_does_not_open_a_connection(self, mock_connect):
        self.assertEqual(load_site_profiles([]), 0)
        mock_connect.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("etl_worker.load.psycopg.connect")
    def test_missing_configuration_fails_before_connecting(self, mock_connect):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            load_site_profiles([PROFILE])
        mock_connect.assert_not_called()


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "Définir TEST_DATABASE_URL pour les tests PostgreSQL.",
)
class LoadSiteProfilesPostgresTests(unittest.TestCase):
    def setUp(self):
        base_url = os.environ["TEST_DATABASE_URL"]
        schema_name = f"test_site_profiles_{uuid4().hex}"
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
        self.connection.execute(_SCHEMA)
        self.connection.execute(
            "INSERT INTO sites SELECT 'SITE00' || n FROM generate_series(1, 7) AS n"
        )
        self.database_url = make_conninfo(
            base_url, options=f"-c search_path={schema_name}"
        )

    def stored_profiles(self):
        return self.connection.execute(
            "SELECT * FROM site_profiles ORDER BY site_id"
        ).fetchall()

    def test_inserts_profile_in_database_format(self):
        self.assertEqual(load_site_profiles([PROFILE], self.database_url), 1)

        stored = self.stored_profiles()[0]
        self.assertEqual(stored["working_days"], [1, 2, 3, 4, 5])
        self.assertEqual(
            (stored["working_hour_start"], stored["working_hour_end"]), (8, 19)
        )
        self.assertEqual(stored["base_consumption"], Decimal("50.00"))
        self.assertEqual(stored["seasonal_variation"], Decimal("0.3000"))
        self.assertIsNone(stored["weekend_factor"])
        self.assertFalse(stored["shift_pattern"])

    def test_loading_twice_changes_nothing(self):
        load_site_profiles([PROFILE], self.database_url)
        before = self.stored_profiles()

        self.assertEqual(load_site_profiles([PROFILE], self.database_url), 0)

        self.assertEqual(self.stored_profiles(), before)

    def test_changed_profile_is_updated(self):
        load_site_profiles([PROFILE], self.database_url)
        changed = PROFILE | {"peak_consumption": 180, "weekend_factor": 1.2}

        self.assertEqual(load_site_profiles([changed], self.database_url), 1)

        stored = self.stored_profiles()[0]
        self.assertEqual(stored["peak_consumption"], Decimal("180.00"))
        self.assertEqual(stored["weekend_factor"], Decimal("1.2000"))

    def test_profile_without_site_in_database_is_skipped(self):
        unknown = PROFILE | {"site_id": "SITE999"}

        self.assertEqual(load_site_profiles([PROFILE, unknown], self.database_url), 1)

        self.assertEqual(
            [row["site_id"] for row in self.stored_profiles()], ["SITE001"]
        )

    def test_invalid_profile_rolls_back_the_entire_batch(self):
        load_site_profiles([PROFILE], self.database_url)
        before = self.stored_profiles()
        changed = PROFILE | {"peak_consumption": 180}
        invalid = PROFILE | {"site_id": "SITE002", "working_days": [0, 7]}

        with self.assertRaises(psycopg.errors.CheckViolation):
            load_site_profiles([changed, invalid], self.database_url)

        self.assertEqual(self.stored_profiles(), before)

    def test_shipped_profiles_satisfy_every_constraint(self):
        profiles = read_site_profiles()

        self.assertEqual(load_site_profiles(profiles, self.database_url), len(profiles))
