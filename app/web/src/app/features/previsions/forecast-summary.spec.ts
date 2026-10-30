import { PredictionPoint } from '../../core/models/prediction';
import { coveredUntil, forecastEnergy, forecastPeak, latestRun } from './forecast-summary';

const NOW = new Date('2026-10-26T10:20:00Z');

function point(
  hour: number,
  kwh: number | null,
  generatedAt = '2026-10-26T09:05:00Z',
): PredictionPoint {
  const ts = new Date(Date.UTC(2026, 9, 26, hour)).toISOString();
  return kwh === null
    ? {
        ts,
        predictionKwh: null,
        runId: null,
        modelName: null,
        modelVersion: null,
        generatedAt: null,
      }
    : { ts, predictionKwh: kwh, runId: 'r', modelName: 'hourly', modelVersion: '3', generatedAt };
}

describe('forecast-summary', () => {
  // 08:00 and 09:00 are past; 10:00 is in progress; 13:00 has no forecast.
  const points = [
    point(8, 900),
    point(9, 500),
    point(10, 300),
    point(11, 700),
    point(12, 400),
    point(13, null),
  ];

  it('cherche le pic parmi l’heure en cours et les suivantes', () => {
    expect(forecastPeak(points, NOW)).toEqual({ kw: 700, ts: '2026-10-26T11:00:00.000Z' });
    expect(forecastPeak([point(8, 900)], NOW)).toBeNull();
  });

  it('additionne l’énergie prévue des heures à venir', () => {
    expect(forecastEnergy(points, NOW)).toBe(1400);
    expect(forecastEnergy([point(13, null)], NOW)).toBeNull();
  });

  it('donne la fin de la dernière heure prévue', () => {
    expect(coveredUntil(points)).toBe('2026-10-26T13:00:00.000Z');
    expect(coveredUntil([point(13, null)])).toBeNull();
  });

  it('retient la série publiée le plus récemment', () => {
    const run = latestRun([
      point(9, 1, '2026-10-26T08:05:00Z'),
      point(10, 1, '2026-10-26T10:05:00Z'),
    ]);
    expect(run).toEqual({
      modelName: 'hourly',
      modelVersion: '3',
      generatedAt: '2026-10-26T10:05:00Z',
    });
    expect(latestRun([point(13, null)])).toBeNull();
  });
});
