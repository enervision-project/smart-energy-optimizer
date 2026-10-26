-- Columns of sites and readings_raws read by ReadingRepository (changesets 002 and 005 of infra/db/changelog).
CREATE TABLE sites (
    site_id     TEXT PRIMARY KEY,
    site_name   TEXT NOT NULL,
    site_type   TEXT NOT NULL,
    capacity_kw DOUBLE PRECISION NOT NULL
);

CREATE TABLE readings_raws (
    site_id                TEXT NOT NULL REFERENCES sites (site_id),
    ts                     TIMESTAMPTZ NOT NULL,
    consumption_kw         DOUBLE PRECISION,
    voltage_v              DOUBLE PRECISION,
    current_a              DOUBLE PRECISION,
    power_factor           DOUBLE PRECISION,
    temperature_celsius    DOUBLE PRECISION,
    humidity_percent       DOUBLE PRECISION,
    null_reasons           TEXT[] NOT NULL DEFAULT '{}',
    data_quality           TEXT NOT NULL,
    source                 TEXT NOT NULL DEFAULT 'current',
    consumption_kw_imputed DOUBLE PRECISION,
    imputation_method      TEXT,
    PRIMARY KEY (site_id, ts)
);

INSERT INTO sites VALUES
    ('SITE001', 'Bureau Paris La Défense', 'office', 200),
    ('SITE003', 'Data Center Marseille', 'datacenter', 800);
