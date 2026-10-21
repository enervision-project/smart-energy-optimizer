--liquibase formatted sql

--changeset enervision:002-initial-schema splitStatements:false
--comment: Schéma complet ; IF NOT EXISTS partout : sur une base existante, seules les tables manquantes sont créées.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Utilisateurs de la plateforme (core-api, module user : entité com.enervision.user.entity.User)
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

-- Profil de référence d'un site (core-api, module configuration : entité SiteProfile).
-- Au plus un profil par site ; rempli par un script dédié, jamais par l'API.
CREATE TABLE IF NOT EXISTS site_profiles (
    site_id             TEXT PRIMARY KEY REFERENCES sites (site_id) ON DELETE CASCADE,
    -- consommations de repos et de pic attendues (kW)
    base_consumption    NUMERIC(14, 2) NOT NULL CHECK (base_consumption >= 0),
    peak_consumption    NUMERIC(14, 2) NOT NULL,
    -- plage d'activité [début, fin[ en heures ; 0 et 24 pour un site actif 24h/24
    working_hour_start  SMALLINT NOT NULL CHECK (working_hour_start BETWEEN 0 AND 23),
    working_hour_end    SMALLINT NOT NULL CHECK (working_hour_end BETWEEN 1 AND 24),
    -- jours d'activité, numérotation ISO : 1 = lundi … 7 = dimanche
    working_days        SMALLINT[] NOT NULL
        CHECK (working_days <@ '{1,2,3,4,5,6,7}'::SMALLINT[] AND cardinality(working_days) > 0),
    -- ratios (ex. 0.15 = ±15 %)
    seasonal_variation  NUMERIC(5, 4) CHECK (seasonal_variation >= 0),
    noise_level         NUMERIC(5, 4) CHECK (noise_level >= 0),
    -- multiplicateur de consommation le week-end (ex. 1.2 = +20 %), si le site en a un
    weekend_factor      NUMERIC(5, 4) CHECK (weekend_factor > 0),
    shift_pattern       BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT site_profiles_peak_above_base_check CHECK (peak_consumption >= base_consumption),
    CONSTRAINT site_profiles_working_hours_check CHECK (working_hour_start < working_hour_end)
);

-- Sites visibles par chaque utilisateur de rôle USER (un ADMIN voit tous les sites, sans ligne ici).
CREATE TABLE IF NOT EXISTS users_sites (
    user_id  UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    site_id  TEXT NOT NULL REFERENCES sites (site_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, site_id)
);

-- Recherche inverse : quels utilisateurs voient un site
CREATE INDEX IF NOT EXISTS users_sites_site_id_idx ON users_sites (site_id);

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

-- Alertes reçues de GET /api/v1/alerts.
CREATE TABLE IF NOT EXISTS alerts (
    alert_id   TEXT PRIMARY KEY,
    "timestamp" TIMESTAMPTZ NOT NULL,
    site_id    TEXT NOT NULL REFERENCES sites (site_id),
    severity   TEXT NOT NULL,
    type       TEXT NOT NULL,
    message    TEXT NOT NULL,
    value      DOUBLE PRECISION,
    threshold  DOUBLE PRECISION NOT NULL,
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alerts_site_timestamp_idx
    ON alerts (site_id, "timestamp" DESC);

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
