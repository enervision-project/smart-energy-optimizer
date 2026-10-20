import { Telemetry } from '../../core/models/telemetry';

export interface TelemetrySummary {
  /** Somme des mesures disponibles (kWh). */
  energyKwh: number;
  peak: { kwh: number; measured_at: string } | null;
  /** Part des points ayant une valeur (mesurée ou imputée), entre 0 et 1. */
  availability: number;
  imputedPoints: number;
  totalPoints: number;
}

export function isImputed(reading: Telemetry): boolean {
  return reading.consumption_kwh !== null && reading.correction_reason !== null;
}

export function summarize(readings: Telemetry[]): TelemetrySummary {
  let energyKwh = 0;
  let available = 0;
  let imputedPoints = 0;
  let peak: TelemetrySummary['peak'] = null;

  for (const r of readings) {
    if (r.consumption_kwh === null) {
      continue;
    }
    available++;
    energyKwh += r.consumption_kwh;
    if (isImputed(r)) {
      imputedPoints++;
    }
    if (!peak || r.consumption_kwh > peak.kwh) {
      peak = { kwh: r.consumption_kwh, measured_at: r.measured_at };
    }
  }

  return {
    energyKwh,
    peak,
    availability: readings.length ? available / readings.length : 0,
    imputedPoints,
    totalPoints: readings.length,
  };
}
