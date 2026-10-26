--liquibase formatted sql

--changeset enervision:007-monitoring-role splitStatements:false
-- Role used by the Postgres exporter (Alloy): server statistics through pg_monitor, no table data.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring') THEN
        CREATE ROLE monitoring LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 3;
    END IF;
END
$$;
GRANT pg_monitor TO monitoring;

--changeset enervision:007-monitoring-role-password runAlways:true runOnChange:true
-- Password from the MONITORING_DB_PASSWORD environment variable of the migrate service (SSM in production).
-- Applied on every migration: a new value in SSM is picked up on the next deploy.
ALTER ROLE monitoring PASSWORD '${MONITORING_DB_PASSWORD}';
