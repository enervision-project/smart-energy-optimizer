export const DATA_QUALITIES = ['good', 'partial', 'degraded', 'critical'] as const;
export type DataQuality = (typeof DATA_QUALITIES)[number];

/** core-api caps the period at 48 h for `1m`, 31 days for `15m`. */
export const READING_STEPS = ['1m', '15m', '1h'] as const;
export type ReadingStep = (typeof READING_STEPS)[number];

/** The ETL collects one reading per site per minute. */
export const READING_REFRESH_MS = 60_000;
/** Beyond this, the last reading is too old: collection has stopped. */
export const STALE_AFTER_SECONDS = 180;

/** A step without readings is still returned, with `null` values: it shows as a gap. */
export interface ReadingPoint {
  ts: string;
  consumptionKw: number | null;
  /** Raw values completed by imputed ones (dashed line). */
  consumptionKwImputed: number | null;
  voltageV: number | null;
  currentA: number | null;
  powerFactor: number | null;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  dataQuality: DataQuality | null;
  nullReasons: string[];
  minutesExpected: number;
  minutesReceived: number;
  minutesBackfilled: number;
  minutesImputed: number;
  imputationMethods: string[];
}

export interface ReadingSeries {
  siteId: string;
  step: ReadingStep;
  from: string;
  to: string;
  points: ReadingPoint[];
}

export interface LatestReading {
  siteId: string;
  ts: string;
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

export interface ReadingSummary {
  siteId: string;
  from: string;
  to: string;
  /** Sum of the hourly raw power averages; hours without a value are excluded. */
  energyKwh: number | null;
  hoursWithData: number;
  hoursExpected: number;
  peakKw: number | null;
  peakAt: string | null;
  availabilityPercent: number | null;
  minutesExpected: number;
  minutesReceived: number;
  minutesWithConsumption: number;
  minutesImputed: number;
}
