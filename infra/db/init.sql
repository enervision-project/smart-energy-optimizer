-- Schéma initial EnerVision.
-- Exécuté automatiquement par l'image TimescaleDB au premier démarrage (volume vide),
-- via /docker-entrypoint-initdb.d/ (voir compose.yaml).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Sites suivis (GET /api/v1/sites)
CREATE TABLE IF NOT EXISTS sites (
    site_id      TEXT PRIMARY KEY,
    site_name    TEXT NOT NULL,
    site_type    TEXT NOT NULL,
    location     TEXT,
    capacity_kw  DOUBLE PRECISION NOT NULL CHECK (capacity_kw > 0),
    status       TEXT NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mesures énergétiques (GET /api/v1/sites/{site_id}/current, /api/v1/readings)
-- Les mesures peuvent être nulles (capteur en panne) : seules les colonnes clés sont NOT NULL.
CREATE TABLE IF NOT EXISTS readings_raws (
    site_id             TEXT NOT NULL REFERENCES sites (site_id),
    ts                  TIMESTAMPTZ NOT NULL,
    site_type           TEXT,
    consumption_kw      DOUBLE PRECISION,
    consumption_kwh     DOUBLE PRECISION,
    voltage_v           DOUBLE PRECISION,
    current_a           DOUBLE PRECISION,
    power_factor        DOUBLE PRECISION,
    temperature_celsius DOUBLE PRECISION,
    humidity_percent    DOUBLE PRECISION,
    null_reasons TEXT[] NOT NULL DEFAULT '{}',
    data_quality        TEXT NOT NULL
        CHECK (data_quality IN ('good', 'partial', 'degraded', 'critical')),
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- la clé primaire d'une hypertable doit contenir la colonne de temps ;
    -- elle sert aussi à dédupliquer les mesures (ON CONFLICT (site_id, ts) DO NOTHING)
    PRIMARY KEY (site_id, ts)
);

-- Hypertable TimescaleDB : découpage automatique en chunks de 7 jours (crée l'index sur ts)
SELECT create_hypertable('readings_raws', by_range('ts', INTERVAL '7 days'), if_not_exists => TRUE);
