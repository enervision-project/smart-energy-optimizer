export type DataQuality = 'good' | 'partial' | 'degraded' | 'critical';

/**
 * Mesure horaire d'un site (table `readings`).
 * Une mesure absente reste `null` : elle est affichée comme un trou, jamais filtrée.
 */
export interface Reading {
  site_id: string;
  ts: string; // timestamptz ISO 8601, début de l'heure
  consumption_kw: number | null;
  consumption_kwh: number | null;
  voltage_v: number | null;
  current_a: number | null;
  power_factor: number | null;
  temperature_celsius: number | null;
  humidity_percent: number | null;
  data_quality: DataQuality;
}
