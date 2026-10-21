-- Ajoute le champ API site_type aux colonnes de mesures.
-- Retire le stockage JSON ajoute precedemment.
BEGIN;

ALTER TABLE public.readings_raws ADD COLUMN IF NOT EXISTS site_type TEXT;
ALTER TABLE public.readings_raws DROP COLUMN IF EXISTS raw_payload;

COMMIT;
