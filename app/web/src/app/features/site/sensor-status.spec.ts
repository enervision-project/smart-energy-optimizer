import { LatestReading } from '../../core/models/reading';
import { imputationLabel, nullReasonLabel, sensorStatuses } from './sensor-status';

function latest(nullReasons: string[], ageSeconds = 30): LatestReading {
  return {
    siteId: 'SITE001',
    ts: '2026-10-26T10:06:00Z',
    ageSeconds,
    source: 'current',
    consumptionKw: 120,
    consumptionKwImputed: null,
    imputationMethod: null,
    voltageV: 230,
    currentA: 10,
    powerFactor: 0.92,
    temperatureCelsius: 21,
    humidityPercent: 40,
    nullReasons,
    dataQuality: nullReasons.length ? 'partial' : 'good',
  };
}

function states(reading: LatestReading | null): Record<string, string> {
  return Object.fromEntries(sensorStatuses(reading).map((s) => [s.key, s.state]));
}

describe('sensorStatuses', () => {
  it('signale le capteur en panne et laisse les autres OK', () => {
    expect(states(latest(['temperature_sensor_failure']))).toEqual({
      consumption: 'ok',
      electrical: 'ok',
      temperature: 'failing',
      humidity: 'ok',
      network: 'ok',
    });
  });

  it('ne déclare que le réseau en panne en cas de perte réseau', () => {
    expect(states(latest(['network_loss']))).toEqual({
      consumption: 'unknown',
      electrical: 'unknown',
      temperature: 'unknown',
      humidity: 'unknown',
      network: 'failing',
    });
  });

  it('n’affiche jamais OK sans mesure récente', () => {
    expect(new Set(Object.values(states(latest([], 600))))).toEqual(new Set(['unknown']));
    expect(new Set(Object.values(states(null)))).toEqual(new Set(['unknown']));
  });

  it('traduit les raisons et les méthodes connues et garde les autres telles quelles', () => {
    expect(nullReasonLabel('network_loss')).toBe('perte réseau');
    expect(nullReasonLabel('autre')).toBe('autre');
    expect(imputationLabel('linear')).toBe('interpolation linéaire');
  });
});
