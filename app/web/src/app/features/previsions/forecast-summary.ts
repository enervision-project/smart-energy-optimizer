import { PredictionPoint } from '../../core/models/prediction';

const HOUR_MS = 3_600_000;

function upcoming(points: PredictionPoint[], now: Date): PredictionPoint[] {
  return points.filter((p) => Date.parse(p.ts) + HOUR_MS > now.getTime());
}

export function forecastPeak(
  points: PredictionPoint[],
  now: Date,
): { kw: number; ts: string } | null {
  let peak: { kw: number; ts: string } | null = null;
  for (const p of upcoming(points, now)) {
    if (p.predictionKwh !== null && (!peak || p.predictionKwh > peak.kw)) {
      peak = { kw: p.predictionKwh, ts: p.ts };
    }
  }
  return peak;
}

export function forecastEnergy(points: PredictionPoint[], now: Date): number | null {
  const values = upcoming(points, now).flatMap((p) =>
    p.predictionKwh === null ? [] : [p.predictionKwh],
  );
  return values.length ? values.reduce((sum, kwh) => sum + kwh, 0) : null;
}

export function coveredUntil(points: PredictionPoint[]): string | null {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].predictionKwh !== null) {
      return new Date(Date.parse(points[i].ts) + HOUR_MS).toISOString();
    }
  }
  return null;
}

export function latestRun(
  points: PredictionPoint[],
): { modelName: string; modelVersion: string; generatedAt: string } | null {
  let latest: { modelName: string; modelVersion: string; generatedAt: string } | null = null;
  for (const p of points) {
    if (
      p.modelName &&
      p.modelVersion &&
      p.generatedAt &&
      (!latest || Date.parse(p.generatedAt) > Date.parse(latest.generatedAt))
    ) {
      latest = { modelName: p.modelName, modelVersion: p.modelVersion, generatedAt: p.generatedAt };
    }
  }
  return latest;
}
