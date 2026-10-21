--liquibase formatted sql

--changeset enervision:004-create-site-profiles-and-users-sites splitStatements:false
--comment: Profil de référence des sites et visibilité des sites par utilisateur (core-api, module configuration).

-- Profil de référence d'un site (entité SiteProfile) : au plus un profil par site, rempli par l'ETL, jamais par l'API.
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
