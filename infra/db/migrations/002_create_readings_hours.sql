-- Table des agrégats horaires pour les bases déjà initialisées.
-- Les données brutes sont conservées sans modification.
BEGIN;

CREATE TABLE IF NOT EXISTS public.readings_hours (
    site_id             TEXT NOT NULL REFERENCES public.sites (site_id),
    ts                  TIMESTAMPTZ NOT NULL,
    consumption_kwh     DOUBLE PRECISION,
    voltage_v           DOUBLE PRECISION,
    current_a           DOUBLE PRECISION,
    power_factor        DOUBLE PRECISION,
    temperature_celsius DOUBLE PRECISION,
    humidity_percent    DOUBLE PRECISION,
    PRIMARY KEY (site_id, ts)
);

COMMIT;
