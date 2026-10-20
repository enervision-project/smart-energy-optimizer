/**
 * Mesure nettoyée (table `telemetry_silver`).
 * Une mesure absente garde `consumption_kwh: null` : elle est affichée comme un trou, jamais filtrée.
 * Une mesure corrigée (imputée) porte un `correction_reason`.
 */
export interface Telemetry {
  measured_at: string;
  site_id: string;
  consumption_kwh: number | null;
  /** Valeurs exactes à fixer avec l'équipe ETL ; le mock utilise `valid`, `imputed`, `missing`. */
  quality_status: string;
  correction_reason: string | null;
}
