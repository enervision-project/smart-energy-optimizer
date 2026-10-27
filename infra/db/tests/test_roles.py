"""Integration tests against disposable TimescaleDB, never the application's DB.

Run: python3 -m unittest discover -s infra/db/tests -v
Docker is required. Container names are unique and cleanup runs even after failures.
"""

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TIMESCALE = os.environ.get("TIMESCALE_TEST_IMAGE", "timescale/timescaledb:2.30.2-pg16")
LIQUIBASE = "liquibase/liquibase:4.33.0"
DATABASE = "roles_test"
ACCOUNTS = {
    "enervision_migrator": "MIGRATOR_DB_PASSWORD",
    "core_api": "CORE_API_DB_PASSWORD",
    "etl_worker": "ETL_DB_PASSWORD",
    "prediction_jobs": "PREDICTION_DB_PASSWORD",
    "monitoring": "MONITORING_DB_PASSWORD",
}


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        **kwargs,
    )


class ServiceRolesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = DATABASE
        cls.container = "enervision-roles-test-" + secrets.token_hex(6)
        cls.passwords = {key: secrets.token_hex(24) for key in ACCOUNTS.values()}
        cls.admin_password = secrets.token_hex(24)
        cls.addClassCleanup(docker, "rm", "-f", cls.container)
        result = docker(
            "run",
            "-d",
            "--name",
            cls.container,
            "--network",
            "none",
            "-e",
            "POSTGRES_DB=" + DATABASE,
            "-e",
            "POSTGRES_PASSWORD=" + cls.admin_password,
            "--mount",
            f"type=bind,src={ROOT / 'infra/db'},dst=/db,readonly",
            TIMESCALE,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        for _ in range(60):
            readiness = cls.sql("SELECT 1", check=False, database="postgres")
            if readiness.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(
                "TimescaleDB did not become ready: "
                + readiness.stderr
                + docker("logs", cls.container).stdout
                + docker("logs", cls.container).stderr
            )
        # initdb's loopback trust rules precede the image's appended host rule.
        # Require SCRAM here so rotation tests exercise authentication, not trust.
        auth = docker(
            "exec",
            cls.container,
            "sh",
            "-c",
            'printf "local all all trust\\nhost all all 127.0.0.1/32 scram-sha-256\\n" '
            '> "$PGDATA/pg_hba.conf"',
        )
        if auth.returncode:
            raise RuntimeError(auth.stderr)
        cls.sql("SELECT pg_reload_conf()")
        cls.bootstrap()
        cls.migrate()
        cls.sql("""
            INSERT INTO sites(site_id, site_name, site_type, capacity_kw, status)
            VALUES ('test', 'Test site', 'office', 10, 'active');
            INSERT INTO site_profiles(site_id, base_consumption, peak_consumption,
                working_hour_start, working_hour_end, working_days)
            VALUES ('test', 1, 2, 8, 18, '{1,2,3,4,5}');
        """)

    @classmethod
    def sql(cls, query, role="postgres", check=True, database=None, password=None):
        credential = (
            password
            if password is not None
            else (
                cls.admin_password
                if role == "postgres"
                else cls.passwords[ACCOUNTS[role]]
            )
        )
        result = docker(
            "exec",
            "-i",
            "-e",
            "PGPASSWORD=" + credential,
            cls.container,
            "psql",
            "-X",
            "-h",
            "127.0.0.1",
            "-U",
            role,
            "-d",
            database or cls.database,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            input=query,
        )
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    @classmethod
    def bootstrap(cls):
        env = ["-e", "PGDATABASE=" + cls.database]
        for key, value in cls.passwords.items():
            env.extend(["-e", key + "=" + value])
        result = docker(
            "exec",
            *env,
            cls.container,
            "psql",
            "-X",
            "-U",
            "postgres",
            "-d",
            cls.database,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "/db/bootstrap.sql",
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def migrate(cls, admin=False, directory=None):
        query = (
            ""
            if admin
            else "?currentSchema=public&options=-c%20role%3Denervision_owner"
        )
        role = "postgres" if admin else "enervision_migrator"
        password = (
            cls.admin_password if admin else cls.passwords["MIGRATOR_DB_PASSWORD"]
        )
        env = os.environ | {"LIQUIBASE_COMMAND_PASSWORD": password}
        result = docker(
            "run",
            "--rm",
            "--network",
            "container:" + cls.container,
            "--mount",
            f"type=bind,src={directory or ROOT / 'infra/db/changelog'},"
            "dst=/liquibase/changelog,readonly",
            "-e",
            "LIQUIBASE_COMMAND_PASSWORD",
            "-e",
            "MONITORING_DB_PASSWORD=legacy-test",
            LIQUIBASE,
            "--search-path=/liquibase/changelog",
            "--changelog-file=changelog.yaml",
            "--url=jdbc:postgresql://127.0.0.1:5432/" + cls.database + query,
            "--username=" + role,
            "update",
            env=env,
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    def denied(self, query, role):
        result = self.sql(query, role=role, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied", result.stderr)

    def test_runtime_accounts_have_no_elevated_attributes_or_memberships(self):
        result = self.sql("""
            SELECT count(*) FROM pg_roles
            WHERE rolname IN ('core_api', 'etl_worker', 'prediction_jobs')
              AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
            SELECT count(*) FROM pg_auth_members
            WHERE member IN (SELECT oid FROM pg_roles
                WHERE rolname IN ('core_api', 'etl_worker', 'prediction_jobs'));
        """)
        self.assertEqual(result.stdout.splitlines(), ["0", "0"])

    def test_tables_belong_to_nologin_owner(self):
        result = self.sql("""
            SELECT count(*) FROM pg_tables
            WHERE schemaname = 'public' AND tableowner <> 'enervision_owner';
            SELECT rolcanlogin FROM pg_roles WHERE rolname = 'enervision_owner';
        """)
        self.assertEqual(result.stdout.splitlines(), ["0", "f"])

    def test_core_can_bootstrap_admin_and_update_role(self):
        self.sql(
            """
            BEGIN;
            INSERT INTO users(email,password,first_name,last_name,company_name,role)
            VALUES ('roles@test.local','test-hash','Test','User','Test','USER');
            UPDATE users SET role='ADMIN' WHERE email='roles@test.local';
            SELECT * FROM users_sites;
            SELECT * FROM sites; SELECT * FROM site_profiles;
            SELECT * FROM readings_raws; SELECT * FROM readings_hours;
            SELECT * FROM alerts; SELECT * FROM predictions; SELECT * FROM prediction_runs;
            ROLLBACK;
        """,
            role="core_api",
        )

    def test_etl_upserts_and_imputation_create_chunks(self):
        self.sql(
            """
            BEGIN;
            INSERT INTO sites(site_id,site_name,site_type,capacity_kw,status)
            VALUES ('test','Test','office',10,'active')
            ON CONFLICT(site_id) DO UPDATE SET site_name=EXCLUDED.site_name;
            INSERT INTO site_profiles(site_id,base_consumption,peak_consumption,
                working_hour_start,working_hour_end,working_days)
            VALUES ('test',1,2,8,18,'{1,2,3,4,5}')
            ON CONFLICT(site_id) DO UPDATE SET peak_consumption=EXCLUDED.peak_consumption;
            INSERT INTO readings_raws(site_id,ts,data_quality)
            VALUES ('test','2040-01-01','good'), ('test','2040-02-01','partial')
            ON CONFLICT(site_id,ts) DO NOTHING;
            UPDATE readings_raws SET consumption_kw_imputed=1,imputation_method='linear'
            WHERE site_id='test' AND consumption_kw IS NULL;
            INSERT INTO readings_hours(site_id,ts,consumption_kwh)
            SELECT site_id,date_trunc('hour',ts),avg(consumption_kw_imputed)
            FROM readings_raws GROUP BY site_id,date_trunc('hour',ts)
            ON CONFLICT(site_id,ts) DO UPDATE SET consumption_kwh=EXCLUDED.consumption_kwh;
            INSERT INTO alerts(alert_id,"timestamp",site_id,severity,type,message,threshold)
            VALUES ('test',now(),'test','high','test','test',1)
            ON CONFLICT(alert_id) DO NOTHING;
            INSERT INTO alerts(alert_id,"timestamp",site_id,severity,type,message,threshold)
            VALUES ('test',now(),'test','high','test','test',1)
            ON CONFLICT(alert_id) DO NOTHING;
            ROLLBACK;
        """,
            role="etl_worker",
        )

    def test_prediction_claims_job_and_publishes_forecast(self):
        self.sql(
            """
            BEGIN;
            SELECT pg_try_advisory_lock(576002);
            SELECT * FROM sites JOIN site_profiles USING(site_id);
            SELECT * FROM readings_hours;
            INSERT INTO prediction_jobs(job_type,schedule_key,trigger_type,status)
            VALUES ('forecast','test','test','running')
            ON CONFLICT(job_type,schedule_key) DO UPDATE SET status='running'
            RETURNING job_id;
            UPDATE prediction_jobs SET status='succeeded',finished_at=now();
            INSERT INTO prediction_runs(job_id,model_name,model_version,window_start,
                window_end,site_count,prediction_count,status)
            SELECT job_id,'test','1',now(),now()+interval '1 hour',1,1,'complete'
            FROM prediction_jobs RETURNING run_id;
            INSERT INTO predictions(run_id,site_id,predicted_for,prediction_kwh)
            SELECT run_id,'test',now(),1 FROM prediction_runs;
            SELECT * FROM predictions JOIN prediction_runs USING(run_id);
            SELECT pg_advisory_unlock(576002);
            ROLLBACK;
        """,
            role="prediction_jobs",
        )

    def test_cross_service_access_is_denied(self):
        for role, query in [
            ("etl_worker", "SELECT * FROM users"),
            ("etl_worker", "SELECT * FROM users_sites"),
            ("etl_worker", "SELECT message FROM alerts"),
            ("prediction_jobs", "SELECT * FROM users"),
            ("prediction_jobs", "SELECT * FROM readings_raws"),
            ("core_api", "UPDATE readings_raws SET consumption_kw=0"),
            ("core_api", "UPDATE predictions SET prediction_kwh=0"),
            ("core_api", "INSERT INTO users_sites VALUES (gen_random_uuid(),'test')"),
            ("prediction_jobs", "UPDATE readings_hours SET consumption_kwh=0"),
            ("prediction_jobs", "UPDATE predictions SET prediction_kwh=0"),
        ]:
            with self.subTest(role=role, query=query):
                self.denied(query, role)

    def test_runtime_cannot_delete_truncate_or_manage_schema_and_roles(self):
        for role in ("core_api", "etl_worker", "prediction_jobs"):
            for query in (
                "DELETE FROM sites",
                "TRUNCATE sites CASCADE",
                "CREATE TABLE public.forbidden(id INT)",
                "CREATE SCHEMA forbidden",
                "ALTER TABLE sites ADD COLUMN forbidden INT",
                "DROP TABLE sites CASCADE",
                "CREATE ROLE forbidden",
                "SET ROLE enervision_owner",
                "UPDATE databasechangelog SET author='forbidden'",
            ):
                with self.subTest(role=role, query=query):
                    result = self.sql(query, role=role, check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(result.stderr, "permission denied|must be owner")

    def test_monitoring_has_statistics_but_no_business_data(self):
        self.sql("SELECT * FROM pg_stat_database", role="monitoring")
        self.denied("SELECT * FROM users", "monitoring")

    def test_migrator_cannot_administer_roles_or_install_extensions(self):
        self.denied("CREATE ROLE forbidden", "enervision_migrator")
        self.denied("ALTER ROLE core_api SUPERUSER", "enervision_migrator")
        self.denied("CREATE EXTENSION file_fdw", "enervision_migrator")

    def test_public_cannot_connect_to_application_database(self):
        self.sql("CREATE ROLE unrelated LOGIN PASSWORD 'isolated-test'")
        self.addCleanup(self.sql, "DROP ROLE unrelated")
        result = self.sql(
            "SELECT 1", role="unrelated", password="isolated-test", check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied for database", result.stderr)

    def test_repeat_bootstrap_and_migration_preserve_data_and_reconcile_grants(self):
        self.sql("GRANT SELECT ON users TO etl_worker")
        self.bootstrap()
        self.migrate()
        self.denied("SELECT * FROM users", "etl_worker")
        self.assertEqual(self.sql("SELECT count(*) FROM sites").stdout.strip(), "1")

    def test_future_migrations_keep_their_own_table_grants(self):
        self.sql("""
            SET ROLE enervision_owner;
            CREATE TABLE future_permission_test(id INT);
            GRANT SELECT ON future_permission_test TO core_api;
        """)
        self.addCleanup(self.sql, "DROP TABLE future_permission_test")
        self.migrate()
        self.sql("SELECT * FROM future_permission_test", role="core_api")
        self.denied("SELECT * FROM future_permission_test", "etl_worker")

    def test_password_rotation_is_applied_and_quoted_safely(self):
        old = self.passwords["ETL_DB_PASSWORD"]
        self.passwords["ETL_DB_PASSWORD"] = (
            "quote'backslash\\space $() ; " + secrets.token_hex(12)
        )
        try:
            self.bootstrap()
            self.sql("SELECT * FROM sites", role="etl_worker")
            result = self.sql("SELECT 1", role="etl_worker", password=old, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("password authentication failed", result.stderr)
        finally:
            self.passwords["ETL_DB_PASSWORD"] = old
            self.bootstrap()

    def test_upgrade_preserves_legacy_changelog_and_data(self):
        # A second, distinct database is created inside this disposable instance.
        self.sql("CREATE DATABASE legacy_test")
        previous = self.__class__.database
        self.__class__.database = "legacy_test"
        try:
            with tempfile.TemporaryDirectory(
                prefix="enervision-legacy-changelog-"
            ) as tmp:
                directory = Path(tmp)
                directory.chmod(0o755)
                shutil.copytree(
                    ROOT / "infra/db/changelog/changes", directory / "changes"
                )
                includes = [
                    f"  - include: {{file: changes/{path.name}, relativeToChangelogFile: true}}"
                    for path in sorted((directory / "changes").glob("00[1-8]*.sql"))
                ]
                (directory / "changelog.yaml").write_text(
                    "databaseChangeLog:\n" + "\n".join(includes)
                )
                self.migrate(admin=True, directory=directory)
                self.sql("""
                    INSERT INTO sites(site_id,site_name,site_type,capacity_kw,status)
                    VALUES ('legacy','Legacy','office',10,'active');
                    INSERT INTO readings_raws(site_id,ts,data_quality)
                    VALUES ('legacy','2026-01-01','good');
                """)
                history = self.sql(
                    "SELECT id,md5sum FROM databasechangelog ORDER BY id"
                ).stdout
                self.bootstrap()
                self.migrate()
                current = self.sql(
                    "SELECT id,md5sum FROM databasechangelog WHERE id NOT LIKE '009%' ORDER BY id"
                ).stdout
                self.assertEqual(current, history)
                self.assertEqual(
                    self.sql(
                        "SELECT count(*) FROM readings_raws", role="core_api"
                    ).stdout.strip(),
                    "1",
                )
                self.sql(
                    """
                    INSERT INTO readings_raws(site_id,ts,data_quality)
                    VALUES ('legacy','2041-01-01','good');
                """,
                    role="etl_worker",
                )
        finally:
            self.__class__.database = previous


class ComposeIsolationTests(unittest.TestCase):
    def test_development_and_production_do_not_leak_admin_or_sibling_secrets(self):
        env = os.environ | {
            "POSTGRES_USER": "admin_test",
            "POSTGRES_PASSWORD": "admin-test-secret",
            "POSTGRES_DB": DATABASE,
            "JWT_SECRET": secrets.token_hex(32),
            "ENERGY_API_BASE_URL": "http://example.invalid",
            "ETL_DATABASE_URL": "postgresql://etl_worker:etl-test@db/roles_test",
            "PREDICTION_DATABASE_URL": "postgresql://prediction_jobs:ml-test@db/roles_test",
            "CORE_API_DB_PASSWORD": "core-test",
            "MIGRATOR_DB_PASSWORD": "migrate-test",
            "ETL_DB_PASSWORD": "etl-test",
            "PREDICTION_DB_PASSWORD": "ml-test",
            "MONITORING_DB_PASSWORD": "monitor-test",
            "MONITORING_HOST": "127.0.0.1",
            "ECR_REGISTRY": "example.invalid",
            "DOMAIN": "example.invalid",
            "MLFLOW_DB_NAME": "mlflow_test",
            "MLFLOW_DB_USER": "mlflow",
            "MLFLOW_DB_PASSWORD": "mlflow-test",
            "AWS_DEFAULT_REGION": "eu-west-3",
            "MLFLOW_ARTIFACTS_DESTINATION": "s3://test/artifacts",
            "TRAINING_BOOTSTRAP_URI": "s3://test/dataset",
        }
        for production in (False, True):
            args = [
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(ROOT / "compose.yaml"),
            ]
            if production:
                args += ["-f", str(ROOT / "compose.prod.yaml")]
            result = docker(
                *args, "--profile", "*", "config", "--format", "json", env=env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            services = json.loads(result.stdout)["services"]
            for service in (
                "core-api",
                "etl-worker",
                "scheduler",
                "prediction-jobs",
                "prediction-service",
                "migrate",
            ):
                with self.subTest(production=production, service=service):
                    settings = services[service].get("environment", {})
                    self.assertNotIn("POSTGRES_PASSWORD", settings)
                    self.assertNotIn("admin-test-secret", json.dumps(settings))
                    self.assertNotIn("MLFLOW_DB_PASSWORD", settings)
            self.assertEqual(
                services["core-api"]["environment"]["SPRING_DATASOURCE_USERNAME"],
                "core_api",
            )
            self.assertEqual(
                services["scheduler"]["environment"]["DATABASE_URL"],
                env["ETL_DATABASE_URL"],
            )
            self.assertEqual(
                services["prediction-jobs"]["environment"]["DATABASE_URL"],
                env["PREDICTION_DATABASE_URL"],
            )
            self.assertNotIn(
                "DATABASE_URL", services["prediction-service"]["environment"]
            )


if __name__ == "__main__":
    unittest.main()
