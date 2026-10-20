-- Recalcule uniquement les kWh des lignes horaires déjà présentes.
-- Moyenne des kW non NULL × 1 heure ; NULL si aucune puissance disponible.
-- Les autres indicateurs, les timestamps et les données brutes sont conservés.
BEGIN;

UPDATE public.readings_hours AS hourly
SET consumption_kwh = (
    SELECT round(avg(raw.consumption_kw::numeric), 2)
    FROM public.readings_raws AS raw
    WHERE raw.site_id = hourly.site_id
        AND raw.ts >= hourly.ts
        AND raw.ts < hourly.ts + INTERVAL '1 hour'
);

COMMIT;
