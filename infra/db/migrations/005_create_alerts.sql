-- Ajoute les alertes aux bases deja initialisees sans modifier les autres tables.
BEGIN;

-- Alertes reçues de GET /api/v1/alerts.
CREATE TABLE IF NOT EXISTS public.alerts (
    alert_id   TEXT PRIMARY KEY,
    "timestamp" TIMESTAMPTZ NOT NULL,
    site_id    TEXT NOT NULL REFERENCES public.sites (site_id),
    severity   TEXT NOT NULL,
    type       TEXT NOT NULL,
    message    TEXT NOT NULL,
    value      DOUBLE PRECISION,
    threshold  DOUBLE PRECISION NOT NULL,
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alerts_site_timestamp_idx
    ON public.alerts (site_id, "timestamp" DESC);

COMMIT;
