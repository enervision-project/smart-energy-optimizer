-- Schéma initial EnerVision.
-- Exécuté automatiquement par l'image TimescaleDB au premier démarrage (volume vide),
-- via /docker-entrypoint-initdb.d/ (voir compose.yaml).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Utilisateurs de la plateforme (core-api, module user : entité com.enervision.user.entities.User)
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- stocké en minuscules par l'API (normalisation à l'inscription et au login)
    email         TEXT NOT NULL UNIQUE,
    -- hash du mot de passe (BCrypt, préfixe {bcrypt}), jamais le mot de passe en clair
    password      TEXT NOT NULL,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('USER', 'ADMIN')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Valeur par défaut persistante pour les nouvelles connexions à cette base.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET timezone TO %L',
        current_database(), 'Europe/Paris'
    );
END;
$$;

-- Applique également le fuseau à la session qui exécute ce fichier.
SET TIME ZONE 'Europe/Paris';

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

-- Agrégats horaires : même instant UTC, affiché dans le fuseau de la connexion.
-- Seuls les résultats horaires sont arrondis à deux décimales.
CREATE TABLE IF NOT EXISTS readings_hours (
    site_id             TEXT NOT NULL REFERENCES sites (site_id),
    ts                  TIMESTAMPTZ NOT NULL,
    consumption_kwh     NUMERIC(14, 2),
    voltage_v           NUMERIC(14, 2),
    current_a           NUMERIC(14, 2),
    power_factor        NUMERIC(14, 2),
    temperature_celsius NUMERIC(14, 2),
    humidity_percent    NUMERIC(14, 2),
    -- Une ligne par site et par heure, recalculable avec ON CONFLICT DO UPDATE.
    PRIMARY KEY (site_id, ts)
);

-- Hypertable TimescaleDB : découpage automatique en chunks de 7 jours (crée l'index sur ts)
SELECT create_hypertable('readings_raws', by_range('ts', INTERVAL '7 days'), if_not_exists => TRUE);
