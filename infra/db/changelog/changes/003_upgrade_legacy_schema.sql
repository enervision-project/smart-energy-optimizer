--liquibase formatted sql

--changeset enervision:003-upgrade-legacy-schema splitStatements:false
--comment: Aligne les bases antérieures sur 002 (anciennes migrations manuelles 001, 003 et 006). Sans effet sur une base neuve.
ALTER TABLE public.readings_raws
    ADD COLUMN IF NOT EXISTS site_type TEXT,
    ADD COLUMN IF NOT EXISTS null_reasons TEXT[] NOT NULL DEFAULT '{}',
    DROP COLUMN IF EXISTS raw_payload;

-- Agrégats horaires arrondis à deux décimales (anciennement DOUBLE PRECISION).
ALTER TABLE public.readings_hours
    ALTER COLUMN consumption_kwh TYPE NUMERIC(14, 2) USING round(consumption_kwh::numeric, 2),
    ALTER COLUMN voltage_v TYPE NUMERIC(14, 2) USING round(voltage_v::numeric, 2),
    ALTER COLUMN current_a TYPE NUMERIC(14, 2) USING round(current_a::numeric, 2),
    ALTER COLUMN power_factor TYPE NUMERIC(14, 2) USING round(power_factor::numeric, 2),
    ALTER COLUMN temperature_celsius TYPE NUMERIC(14, 2) USING round(temperature_celsius::numeric, 2),
    ALTER COLUMN humidity_percent TYPE NUMERIC(14, 2) USING round(humidity_percent::numeric, 2);
