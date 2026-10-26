-- Forecast schema from changeset 006, isolated from the application database.
CREATE TABLE sites (site_id TEXT PRIMARY KEY);
INSERT INTO sites VALUES ('SITE001'), ('SITE002');

--liquibase formatted sql

--changeset enervision:006-prediction-jobs-and-forecasts splitStatements:false
CREATE TABLE IF NOT EXISTS prediction_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL CHECK (job_type IN ('training', 'forecast')),
    schedule_key TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    detail TEXT,
    UNIQUE (job_type, schedule_key)
);

CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID UNIQUE REFERENCES prediction_jobs(job_id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    site_count INTEGER NOT NULL CHECK (site_count > 0),
    prediction_count INTEGER NOT NULL CHECK (prediction_count > 0),
    status TEXT NOT NULL CHECK (status IN ('complete'))
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES prediction_runs(run_id),
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    predicted_for TIMESTAMPTZ NOT NULL,
    prediction_kwh NUMERIC(14, 3) NOT NULL CHECK (prediction_kwh >= 0),
    UNIQUE (run_id, site_id, predicted_for)
);

CREATE INDEX IF NOT EXISTS predictions_site_hour_idx
    ON predictions(site_id, predicted_for DESC);
CREATE INDEX IF NOT EXISTS prediction_runs_generated_idx
    ON prediction_runs(generated_at DESC);
