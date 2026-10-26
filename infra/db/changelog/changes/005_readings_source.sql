--liquibase formatted sql

--changeset enervision:005-readings-source splitStatements:false
--comment: Origine de chaque mesure brute et complétude des agrégats horaires.

-- current  = GET /sites/{id}/current, mesure prise à l'instant de l'appel ;
-- readings = GET /readings, collecte minute par minute avant le passage à /current ;
-- backfill = GET /readings, rattrapage après coup d'une minute jamais reçue.
-- /readings recalcule ses valeurs à chaque appel : ce ne sont pas des mesures d'époque.
ALTER TABLE readings_raws
    ADD COLUMN source TEXT NOT NULL DEFAULT 'current'
        CHECK (source IN ('current', 'readings', 'backfill'));

-- Passage à /current : PR #180, déployée le 26/10/2026 à 09:50 UTC.
-- Toutes les lignes antérieures ont été collectées via /readings.
UPDATE readings_raws SET source = 'readings' WHERE ts < '2026-10-26 09:50:00+00';

-- Consommation imputée, à côté de la valeur brute qui reste NULL (sujet, PDF 04 p. 13) :
-- previous_value = dernière valeur brute ≤ 15 min avant (datacenter, hôpital) ;
-- linear = interpolation entre deux valeurs brutes distantes d'au plus 3 min (autres sites).
-- Seule la consommation est imputée ; les agrégats horaires n'utilisent que le brut.
ALTER TABLE readings_raws
    ADD COLUMN consumption_kw_imputed DOUBLE PRECISION,
    ADD COLUMN imputation_method TEXT
        CHECK (imputation_method IN ('previous_value', 'linear')),
    ADD CONSTRAINT readings_raws_imputation_check CHECK (
        (consumption_kw_imputed IS NULL) = (imputation_method IS NULL)
        AND (consumption_kw IS NULL OR consumption_kw_imputed IS NULL)
    );

-- Complétude de chaque heure ; NULL = heure calculée avant ce changeset.
-- minutes_received = 0 distingue « aucune mesure reçue » de « capteurs en panne ».
ALTER TABLE readings_hours
    ADD COLUMN minutes_received    SMALLINT,
    ADD COLUMN minutes_consumption SMALLINT,
    ADD COLUMN minutes_backfilled  SMALLINT;
