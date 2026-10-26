export const DATA_QUALITIES = ['good', 'partial', 'degraded', 'critical'] as const;
/** Qualité d'une mesure, de la meilleure à la pire. */
export type DataQuality = (typeof DATA_QUALITIES)[number];

/** Largeur d'un point de courbe ; core-api limite la période à 48 h en `1m`, 31 jours en `15m`. */
export const READING_STEPS = ['1m', '15m', '1h'] as const;
export type ReadingStep = (typeof READING_STEPS)[number];

/** Rafraîchissement des mesures : l'ETL en collecte une par site et par minute. */
export const READING_REFRESH_MS = 60_000;
/** Au-delà, la dernière mesure est trop ancienne : la collecte est arrêtée. */
export const STALE_AFTER_SECONDS = 180;

/**
 * Un pas de la courbe (GET /api/v1/sites/{siteId}/readings). Un pas sans mesure est renvoyé quand même,
 * avec des valeurs `null` et `minutesReceived = 0` : il est affiché comme un trou.
 */
export interface ReadingPoint {
  ts: string;
  /** Moyenne des valeurs brutes. */
  consumptionKw: number | null;
  /** Moyenne des valeurs brutes complétées par les valeurs imputées (ligne pointillée). */
  consumptionKwImputed: number | null;
  voltageV: number | null;
  currentA: number | null;
  powerFactor: number | null;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  /** Pire qualité du pas, `null` sans mesure. */
  dataQuality: DataQuality | null;
  nullReasons: string[];
  /** Minutes du pas déjà écoulées. */
  minutesExpected: number;
  minutesReceived: number;
  /** Minutes avec une consommation brute : couverture de la courbe mesurée. */
  minutesWithConsumption: number;
  minutesBackfilled: number;
  minutesImputed: number;
  imputationMethods: string[];
}

export interface ReadingSeries {
  siteId: string;
  step: ReadingStep;
  from: string;
  /** Fin du dernier pas, exclue. */
  to: string;
  points: ReadingPoint[];
}

/** Dernière mesure d'un site (GET /api/v1/sites/{siteId}/readings/latest). */
export interface LatestReading {
  siteId: string;
  ts: string;
  /** Secondes depuis la minute de la mesure. */
  ageSeconds: number;
  source: string;
  consumptionKw: number | null;
  consumptionKwImputed: number | null;
  imputationMethod: string | null;
  voltageV: number | null;
  currentA: number | null;
  powerFactor: number | null;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  nullReasons: string[];
  dataQuality: DataQuality;
}

/** Synthèse d'un site sur une période, valeurs brutes uniquement (GET …/readings/summary). */
export interface ReadingSummary {
  siteId: string;
  from: string;
  to: string;
  /** Somme des moyennes horaires de la puissance brute ; les heures sans valeur sont exclues. */
  energyKwh: number | null;
  hoursWithData: number;
  hoursExpected: number;
  peakKw: number | null;
  peakAt: string | null;
  /** Minutes avec une consommation brute / minutes écoulées. */
  availabilityPercent: number | null;
  minutesExpected: number;
  minutesReceived: number;
  minutesWithConsumption: number;
  minutesImputed: number;
}
