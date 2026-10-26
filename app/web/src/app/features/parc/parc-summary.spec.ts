import { ParcSiteLoad } from '../../core/models/parc-summary';
import { ReadingPoint, ReadingSeries } from '../../core/models/reading';
import { parcSeries, qualityCounts, sortByLoad, trendsBySite } from './parc-summary';

function site(
  siteId: string,
  kw: number | null,
  dataQuality: ParcSiteLoad['dataQuality'] = 'good',
): ParcSiteLoad {
  return {
    siteId,
    siteName: siteId,
    currentConsumptionKw: kw,
    consumptionImputed: false,
    capacityKw: 100,
    loadPercent: kw,
    dataQuality,
    ts: null,
    ageSeconds: null,
  };
}

function series(siteId: string, values: (number | null)[]): ReadingSeries {
  const points = values.map((kw, i): ReadingPoint => ({
    ts: `2026-10-26T1${i}:00:00Z`,
    consumptionKw: kw,
    consumptionKwImputed: kw,
    voltageV: null,
    currentA: null,
    powerFactor: null,
    temperatureCelsius: null,
    humidityPercent: null,
    dataQuality: kw === null ? null : 'good',
    nullReasons: [],
    minutesExpected: 60,
    minutesReceived: kw === null ? 0 : 60,
    minutesBackfilled: 0,
    minutesImputed: 0,
    imputationMethods: [],
  }));
  return { siteId, step: '1h', from: points[0].ts, to: '', points };
}

describe('parc-summary', () => {
  it('trie par charge décroissante, les sites sans valeur en dernier', () => {
    const sorted = sortByLoad([site('A', 40), site('B', null, null), site('C', 80)]);
    expect(sorted.map((s) => s.siteId)).toEqual(['C', 'A', 'B']);
  });

  it('compte les qualités, sites sans mesure récente compris', () => {
    const sites = [
      site('A', 40),
      site('B', null, null),
      site('C', 80, 'partial'),
      site('D', null, 'critical'),
    ];
    expect(qualityCounts(sites)).toEqual({
      good: 1,
      partial: 1,
      degraded: 0,
      critical: 1,
      none: 1,
    });
  });

  it('additionne les sites pas à pas et signale les pas incomplets', () => {
    const result = parcSeries([series('A', [5, 10]), series('B', [7, null])]);
    expect(result.steps).toEqual(['2026-10-26T10:00:00Z', '2026-10-26T11:00:00Z']);
    expect(result.totals).toEqual([12, 10]);
    expect(result.incomplete).toEqual([false, true]);
  });

  it('renvoie null quand aucun site n’a de valeur, et rien sans série', () => {
    expect(parcSeries([series('A', [null])]).totals).toEqual([null]);
    expect(parcSeries([])).toEqual({ steps: [], totals: [], incomplete: [] });
  });

  it('regroupe les tendances par site', () => {
    expect(trendsBySite([series('A', [1, 2])]).get('A')).toEqual([1, 2]);
  });
});
