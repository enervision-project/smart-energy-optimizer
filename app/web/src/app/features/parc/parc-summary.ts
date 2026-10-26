import { ParcSiteLoad } from '../../core/models/parc-summary';
import { DataQuality, ReadingSeries } from '../../core/models/reading';

export interface ParcSeries {
  /** Début de chaque pas (ISO 8601), dans l'ordre chronologique. */
  steps: string[];
  /** Somme des consommations mesurées (kW), `null` si aucun site n'a de valeur. */
  totals: (number | null)[];
  /** Vrai si au moins un site n'a pas de valeur mesurée sur le pas : le total est sous-estimé. */
  incomplete: boolean[];
}

/** Sites triés par charge décroissante, ceux sans valeur à la fin. */
export function sortByLoad(sites: ParcSiteLoad[]): ParcSiteLoad[] {
  return [...sites].sort((a, b) => (b.loadPercent ?? -1) - (a.loadPercent ?? -1));
}

/** Qualité de la dernière mesure de chaque site ; `none` = pas de mesure récente. */
export function qualityCounts(sites: ParcSiteLoad[]): Record<DataQuality | 'none', number> {
  const counts = { good: 0, partial: 0, degraded: 0, critical: 0, none: 0 };
  for (const s of sites) {
    counts[s.dataQuality ?? 'none']++;
  }
  return counts;
}

/**
 * Consommation du parc pas à pas : somme des valeurs mesurées de chaque site. Les séries ont les mêmes pas
 * (même période, même pas demandés à core-api).
 */
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

/** Consommation mesurée de chaque site, pas à pas, pour les mini-courbes. */
export function trendsBySite(series: ReadingSeries[]): Map<string, (number | null)[]> {
  return new Map(series.map((s) => [s.siteId, s.points.map((p) => p.consumptionKw)]));
}
