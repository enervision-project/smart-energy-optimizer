import { ParcSiteLoad } from '../../core/models/parc-summary';
import { DataQuality, ReadingSeries } from '../../core/models/reading';

export interface ParcSeries {
  steps: string[];
  totals: (number | null)[];
  /** True if a site has no value for the step: the total is underestimated. */
  incomplete: boolean[];
}

export function sortByLoad(sites: ParcSiteLoad[]): ParcSiteLoad[] {
  return [...sites].sort((a, b) => (b.loadPercent ?? -1) - (a.loadPercent ?? -1));
}

export function qualityCounts(sites: ParcSiteLoad[]): Record<DataQuality | 'none', number> {
  const counts = { good: 0, partial: 0, degraded: 0, critical: 0, none: 0 };
  for (const s of sites) {
    counts[s.dataQuality ?? 'none']++;
  }
  return counts;
}

export function parcSeries(series: ReadingSeries[]): ParcSeries {
  const steps = series[0]?.points.map((p) => p.ts) ?? [];
  const byStep = steps.map((ts) =>
    series.map((s) => s.points.find((p) => p.ts === ts)?.consumptionKw ?? null),
  );
  return {
    steps,
    totals: byStep.map((values) => {
      const known = values.filter((v): v is number => v !== null);
      return known.length ? Math.round(known.reduce((sum, kw) => sum + kw, 0) * 10) / 10 : null;
    }),
    incomplete: byStep.map((values) => values.some((v) => v === null)),
  };
}

export function trendsBySite(series: ReadingSeries[]): Map<string, (number | null)[]> {
  return new Map(series.map((s) => [s.siteId, s.points.map((p) => p.consumptionKw)]));
}
