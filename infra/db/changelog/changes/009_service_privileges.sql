--liquibase formatted sql

--changeset enervision:009-service-privileges runAlways:true splitStatements:false
-- Reconcile only these managed tables. Do not revoke grants on future tables:
-- their own migrations define their permissions and may not run again.
REVOKE ALL ON users, users_sites, sites, site_profiles, alerts, readings_raws,
    readings_hours, prediction_jobs, prediction_runs, predictions,
    databasechangelog, databasechangeloglock FROM core_api, etl_worker, prediction_jobs;
REVOKE ALL ON users, users_sites, sites, site_profiles, alerts, readings_raws,
    readings_hours, prediction_jobs, prediction_runs, predictions FROM PUBLIC;

GRANT SELECT ON users, users_sites, sites, site_profiles, readings_raws,
    readings_hours, alerts, prediction_runs, predictions TO core_api;
GRANT INSERT, UPDATE ON users TO core_api;

GRANT SELECT, INSERT, UPDATE ON sites, site_profiles, readings_raws, readings_hours TO etl_worker;
GRANT INSERT ON alerts TO etl_worker;
GRANT SELECT (alert_id) ON alerts TO etl_worker;

GRANT SELECT ON sites, site_profiles, readings_hours TO prediction_jobs;
GRANT SELECT, INSERT, UPDATE ON prediction_jobs TO prediction_jobs;
GRANT SELECT, INSERT ON prediction_runs, predictions TO prediction_jobs;
