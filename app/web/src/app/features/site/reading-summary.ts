import { DataQuality, Reading } from '../../core/models/reading';

export interface ReadingSummary {
  /** Somme des consommations disponibles (kWh). */
  energyKwh: number;
  peak: { kw: number; ts: string } | null;
  /** Part des heures ayant une consommation, entre 0 et 1. */
  availability: number;
  quality: Record<DataQuality, number>;
  totalPoints: number;
}

export function summarize(readings: Reading[]): ReadingSummary {
  let energyKwh = 0;
  let available = 0;
  let peak: ReadingSummary['peak'] = null;
  const quality: Record<DataQuality, number> = { good: 0, partial: 0, degraded: 0, critical: 0 };

  for (const r of readings) {
    quality[r.data_quality]++;
    if (r.consumption_kwh !== null) {
      energyKwh += r.consumption_kwh;
    }
    if (r.consumption_kw === null) {
      continue;
    }
    available++;
    if (!peak || r.consumption_kw > peak.kw) {
      peak = { kw: r.consumption_kw, ts: r.ts };
    }
  }

  return {
    energyKwh,
    peak,
    availability: readings.length ? available / readings.length : 0,
    quality,
    totalPoints: readings.length,
  };
}
