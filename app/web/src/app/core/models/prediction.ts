/**
 * Une heure de prévision (GET /api/v1/sites/{siteId}/predictions de core-api). Une heure sans prévision
 * publiée est renvoyée avec des valeurs `null`.
 */
export interface PredictionPoint {
  /** Début de l'heure (UTC). */
  ts: string;
  /** Énergie prévue sur l'heure, en kWh : c'est aussi la puissance moyenne de l'heure, en kW. */
  predictionKwh: number | null;
  runId: string | null;
  modelName: string | null;
  modelVersion: string | null;
  generatedAt: string | null;
}

/** Prévisions horaires d'un site sur `[from, to)`, issues pour chaque heure de la série complète la plus récente. */
export interface PredictionSeries {
  siteId: string;
  step: '1h';
  from: string;
  to: string;
  points: PredictionPoint[];
}
