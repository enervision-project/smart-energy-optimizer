--liquibase formatted sql

--changeset enervision:001-rename-legacy-readings splitStatements:false
--comment: Bases créées avant le renommage : readings devient readings_raws, données conservées.
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
