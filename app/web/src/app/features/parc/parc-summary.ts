import { ParcSiteSummary } from '../../core/models/parc-summary';
import { DataQuality, Reading } from '../../core/models/reading';

export interface ParcSeries {
  /** Heures (ISO 8601) dans l'ordre chronologique. */
  hours: string[];
  /** Somme des consommations connues (kW), `null` si aucun site n'a de mesure. */
  totals: (number | null)[];
  /** Vrai si au moins un site n'a pas de mesure à cette heure : le total est sous-estimé. */
  incomplete: boolean[];
}

/** Sites triés par charge décroissante, ceux sans mesure à la fin. */
export function sortByLoad(sites: ParcSiteSummary[]): ParcSiteSummary[] {
  return [...sites].sort((a, b) => (b.load_percent ?? -1) - (a.load_percent ?? -1));
}

/** Sites exclus du total faute de mesure récente. */
export function missingSites(sites: ParcSiteSummary[]): ParcSiteSummary[] {
  return sites.filter((s) => s.current_consumption_kw === null);
}

export function qualityCounts(sites: ParcSiteSummary[]): Record<DataQuality, number> {
  const counts: Record<DataQuality, number> = { good: 0, partial: 0, degraded: 0, critical: 0 };
  for (const s of sites) {
    counts[s.data_quality]++;
  }
  return counts;
}

/** Consommation horaire du parc : somme de tous les sites, heure par heure. */
export function parcSeries(readings: Reading[]): ParcSeries {
  const siteCount = new Set(readings.map((r) => r.site_id)).size;
  const byHour = new Map<string, Reading[]>();
  for (const r of readings) {
    byHour.set(r.ts, [...(byHour.get(r.ts) ?? []), r]);
  }
  const hours = [...byHour.keys()].sort();
  const totals = hours.map((h) => {
    const known = byHour
      .get(h)!
      .flatMap((r) => (r.consumption_kw === null ? [] : [r.consumption_kw]));
    return known.length ? Math.round(known.reduce((sum, kw) => sum + kw, 0) * 10) / 10 : null;
  });
  const incomplete = hours.map((h) => {
    const rs = byHour.get(h)!;
    return rs.length < siteCount || rs.some((r) => r.consumption_kw === null);
  });
  return { hours, totals, incomplete };
}

/** Consommation horaire de chaque site, dans l'ordre chronologique. */
export function trendsBySite(readings: Reading[]): Map<string, (number | null)[]> {
  const trends = new Map<string, (number | null)[]>();
  for (const r of [...readings].sort((a, b) => a.ts.localeCompare(b.ts))) {
    trends.set(r.site_id, [...(trends.get(r.site_id) ?? []), r.consumption_kw]);
  }
  return trends;
}
