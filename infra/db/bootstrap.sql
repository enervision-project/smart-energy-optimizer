-- Administration only; run before Liquibase on both new and existing volumes.
-- psql quotes values as SQL literals; passwords never appear in command arguments.
\getenv database PGDATABASE
\getenv migrator_password MIGRATOR_DB_PASSWORD
\getenv core_password CORE_API_DB_PASSWORD
\getenv etl_password ETL_DB_PASSWORD
\getenv prediction_password PREDICTION_DB_PASSWORD
\getenv monitoring_password MONITORING_DB_PASSWORD

BEGIN;
SELECT pg_advisory_xact_lock(576099);
SET password_encryption = 'scram-sha-256';

DO $$
DECLARE
    account TEXT;
BEGIN
    FOREACH account IN ARRAY ARRAY[
        'enervision_owner', 'enervision_migrator', 'core_api',
        'etl_worker', 'prediction_jobs', 'monitoring'
    ] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = account) THEN
            EXECUTE format('CREATE ROLE %I', account);
        END IF;
    END LOOP;
END
$$;

ALTER ROLE enervision_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE enervision_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'migrator_password';
ALTER ROLE core_api LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'core_password';
ALTER ROLE etl_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'etl_password';
ALTER ROLE prediction_jobs LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'prediction_password';
ALTER ROLE monitoring LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3 PASSWORD :'monitoring_password';

-- These managed accounts must not inherit privileges or SET ROLE to other roles.
DO $$
DECLARE
    membership RECORD;
BEGIN
    FOR membership IN
        SELECT parent.rolname AS parent, child.rolname AS child
        FROM pg_auth_members m
        JOIN pg_roles parent ON parent.oid = m.roleid
        JOIN pg_roles child ON child.oid = m.member
        WHERE child.rolname IN (
            'core_api', 'etl_worker', 'prediction_jobs', 'enervision_migrator',
            'enervision_owner', 'monitoring'
        )
    LOOP
        EXECUTE format('REVOKE %I FROM %I', membership.parent, membership.child);
    END LOOP;
END
$$;
GRANT enervision_owner TO enervision_migrator WITH INHERIT FALSE, SET TRUE;
GRANT pg_monitor TO monitoring;

CREATE EXTENSION IF NOT EXISTS timescaledb;
ALTER DATABASE :"database" OWNER TO enervision_owner;
REVOKE ALL ON DATABASE :"database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database" TO
    enervision_owner, enervision_migrator, core_api, etl_worker, prediction_jobs, monitoring;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO enervision_owner;
GRANT USAGE ON SCHEMA public TO core_api, etl_worker, prediction_jobs;

-- Transfer only application objects, never TimescaleDB extension/catalog objects.
-- ALTER TABLE on a hypertable also transfers its chunks through TimescaleDB hooks.
DO $$
DECLARE
    object_name TEXT;
BEGIN
    FOREACH object_name IN ARRAY ARRAY[
        'users', 'sites', 'site_profiles', 'users_sites', 'alerts',
        'readings', 'readings_raws', 'readings_hours', 'prediction_jobs',
        'prediction_runs', 'predictions', 'databasechangelog', 'databasechangeloglock'
    ] LOOP
        IF EXISTS (
            SELECT FROM pg_class
            WHERE oid = to_regclass(format('public.%I', object_name))
              AND pg_get_userbyid(relowner) <> 'enervision_owner'
        ) THEN
            EXECUTE format('ALTER TABLE public.%I OWNER TO enervision_owner', object_name);
        END IF;
    END LOOP;
END
$$;

ALTER ROLE core_api IN DATABASE :"database" SET search_path = public;
ALTER ROLE core_api IN DATABASE :"database" SET application_name = 'core-api';
ALTER ROLE etl_worker IN DATABASE :"database" SET search_path = public;
ALTER ROLE etl_worker IN DATABASE :"database" SET application_name = 'etl-worker';
ALTER ROLE prediction_jobs IN DATABASE :"database" SET search_path = public;
ALTER ROLE prediction_jobs IN DATABASE :"database" SET application_name = 'prediction-jobs';
COMMIT;
