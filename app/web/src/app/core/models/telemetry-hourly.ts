export interface TelemetryHourly {
  bucket_hour: string;             // timestamptz ISO 8601, début de l'heure
  site_id: string;
  avg_consumption_kwh: number | null;   // null = pas de mesure exploitable sur l'heure
  max_consumption_kwh: number | null;
  sample_count?: number;           // nb de mesures dans l'heure — proposé, non validé
  degraded_count?: number;         // nb de mesures nulles ou imputées — proposé, non validé
}
