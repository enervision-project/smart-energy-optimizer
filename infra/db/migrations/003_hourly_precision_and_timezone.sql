-- Arrondit les lignes horaires existantes, sans modifier les mesures brutes.
BEGIN;

ALTER TABLE public.readings_hours
    ALTER COLUMN consumption_kwh TYPE NUMERIC(14, 2)
        USING round(consumption_kwh::numeric, 2),
    ALTER COLUMN voltage_v TYPE NUMERIC(14, 2)
        USING round(voltage_v::numeric, 2),
    ALTER COLUMN current_a TYPE NUMERIC(14, 2)
        USING round(current_a::numeric, 2),
    ALTER COLUMN power_factor TYPE NUMERIC(14, 2)
        USING round(power_factor::numeric, 2),
    ALTER COLUMN temperature_celsius TYPE NUMERIC(14, 2)
        USING round(temperature_celsius::numeric, 2),
    ALTER COLUMN humidity_percent TYPE NUMERIC(14, 2)
        USING round(humidity_percent::numeric, 2);

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

COMMIT;
