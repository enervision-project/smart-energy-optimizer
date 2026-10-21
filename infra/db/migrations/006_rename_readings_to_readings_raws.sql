-- Renomme l'ancienne table en conservant ses donnees.
BEGIN;

DO $migration$
BEGIN
    IF to_regclass('public.readings') IS NOT NULL
       AND to_regclass('public.readings_raws') IS NOT NULL THEN
        RAISE EXCEPTION
            'Les tables public.readings et public.readings_raws existent toutes les deux.'
            USING ERRCODE = '42P07';
    ELSIF to_regclass('public.readings') IS NOT NULL THEN
        ALTER TABLE public.readings RENAME TO readings_raws;
    END IF;
END;
$migration$;

-- Les anciens releves gardent site_type a NULL et un tableau null_reasons vide.
ALTER TABLE public.readings_raws
    ADD COLUMN IF NOT EXISTS site_type TEXT,
    ADD COLUMN IF NOT EXISTS null_reasons TEXT[] NOT NULL DEFAULT '{}';

COMMIT;
