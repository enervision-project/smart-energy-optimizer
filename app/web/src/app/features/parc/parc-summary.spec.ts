import { ParcSiteSummary } from '../../core/models/parc-summary';
import { Reading } from '../../core/models/reading';
import { missingSites, parcSeries, qualityCounts, sortByLoad, trendsBySite } from './parc-summary';

function site(
  site_id: string,
  kw: number | null,
  data_quality: ParcSiteSummary['data_quality'] = 'good',
): ParcSiteSummary {
  return {
    site_id,
    site_name: site_id,
    current_consumption_kw: kw,
    capacity_kw: 100,
    load_percent: kw,
    data_quality,
  };
}

function reading(site_id: string, ts: string, kw: number | null): Reading {
  return {
    site_id,
    ts,
    consumption_kw: kw,
    consumption_kwh: kw,
    voltage_v: null,
    current_a: null,
    power_factor: null,
    temperature_celsius: null,
    humidity_percent: null,
    data_quality: kw === null ? 'critical' : 'good',
  };
}

describe('parc-summary', () => {
  it('trie par charge décroissante, les sites sans mesure en dernier', () => {
    const sorted = sortByLoad([site('A', 40), site('B', null, 'critical'), site('C', 80)]);
    expect(sorted.map((s) => s.site_id)).toEqual(['C', 'A', 'B']);
  });

  it('liste les sites sans mesure et compte les qualités', () => {
    const sites = [site('A', 40), site('B', null, 'critical'), site('C', 80, 'partial')];
    expect(missingSites(sites).map((s) => s.site_id)).toEqual(['B']);
    expect(qualityCounts(sites)).toEqual({ good: 1, partial: 1, degraded: 0, critical: 1 });
  });

  it('additionne les sites heure par heure et signale les heures incomplètes', () => {
    const series = parcSeries([
      reading('A', '2026-10-20T11:00:00.000Z', 10),
      reading('A', '2026-10-20T10:00:00.000Z', 5),
      reading('B', '2026-10-20T10:00:00.000Z', 7),
      reading('B', '2026-10-20T11:00:00.000Z', null),
    ]);
    expect(series.hours).toEqual(['2026-10-20T10:00:00.000Z', '2026-10-20T11:00:00.000Z']);
    expect(series.totals).toEqual([12, 10]);
    expect(series.incomplete).toEqual([false, true]);
  });

  it('renvoie null quand aucun site n’a de mesure', () => {
    expect(parcSeries([reading('A', '2026-10-20T10:00:00.000Z', null)]).totals).toEqual([null]);
  });

  it('regroupe les tendances par site dans l’ordre chronologique', () => {
    const trends = trendsBySite([
      reading('A', '2026-10-20T11:00:00.000Z', 2),
      reading('A', '2026-10-20T10:00:00.000Z', 1),
    ]);
    expect(trends.get('A')).toEqual([1, 2]);
  });
});
