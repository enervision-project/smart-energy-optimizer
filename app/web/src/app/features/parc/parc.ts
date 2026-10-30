import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { forkJoin, of, switchMap, timer } from 'rxjs';
import { ALERT_REFRESH_MS } from '../../core/models/alert';
import { READING_REFRESH_MS } from '../../core/models/reading';
import { reloadOnError } from '../../core/resources/reload-on-error';
import { EnergyApi } from '../../core/services/energy-api';
import { ConsumptionChart } from '../../shared/components/consumption-chart/consumption-chart';
import { KpiCard } from '../../shared/components/kpi-card/kpi-card';
import { Sparkline } from '../../shared/components/sparkline/sparkline';
import { severityLabel } from '../alertes/alert-labels';
import { parcSeries, qualityCounts, sortByLoad, trendsBySite } from './parc-summary';

const HOUR_MS = 3_600_000;
const WINDOW_HOURS = 24;
export const MAX_ALERTS = 4;

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const hour = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
const time = new Intl.DateTimeFormat('fr-FR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

@Component({
  imports: [RouterLink, KpiCard, ConsumptionChart, Sparkline],
  selector: 'app-parc',
  styleUrl: './parc.scss',
  templateUrl: './parc.html',
})
export class Parc {
  private readonly api = inject(EnergyApi);

  protected readonly windowHours = WINDOW_HOURS;
  protected readonly severityLabel = severityLabel;

  protected readonly summaryResource = rxResource({
    stream: () => timer(0, READING_REFRESH_MS).pipe(switchMap(() => this.api.getParcSummary())),
  });

  protected readonly seriesResource = rxResource({
    stream: () =>
      timer(0, READING_REFRESH_MS).pipe(
        switchMap(() => this.api.getSites()),
        switchMap((sites) => {
          const to = new Date();
          const from = new Date(to.getTime() - WINDOW_HOURS * HOUR_MS);
          return sites.length
            ? forkJoin(sites.map((s) => this.api.getReadingSeries(s.siteId, from, to, '1h')))
            : of([]);
        }),
      ),
  });

  protected readonly alertsResource = rxResource({
    stream: () =>
      timer(0, ALERT_REFRESH_MS).pipe(switchMap(() => this.api.getAlerts({}, 0, MAX_ALERTS))),
  });

  constructor() {
    reloadOnError(this.summaryResource, READING_REFRESH_MS);
    reloadOnError(this.seriesResource, READING_REFRESH_MS);
    reloadOnError(this.alertsResource, ALERT_REFRESH_MS);
  }

  private readonly summary = computed(() =>
    this.summaryResource.hasValue() ? this.summaryResource.value() : undefined,
  );
  private readonly series = computed(() =>
    this.seriesResource.hasValue() ? this.seriesResource.value() : [],
  );
  protected readonly alertPage = computed(() =>
    this.alertsResource.hasValue() ? this.alertsResource.value() : undefined,
  );

  protected readonly updatedAt = computed(() => {
    const s = this.summary();
    return s ? time.format(new Date(s.timestamp)) : null;
  });

  protected readonly kpis = computed(() => {
    const s = this.summary();
    if (!s) {
      return [];
    }
    const reporting = s.totalSites - s.sitesWithoutData.length;
    const estimated = s.sites.filter((site) => site.consumptionImputed).length;
    const quality = qualityCounts(s.sites);
    const issues = [
      ...(['partial', 'degraded', 'critical'] as const)
        .filter((q) => quality[q] > 0)
        .map((q) => `${quality[q]} ${q}`),
      ...(quality.none ? [`${quality.none} sans mesure`] : []),
    ];
    return [
      {
        label: 'Consommation instantanée',
        value: `${number.format(s.totalConsumptionKw)} kW`,
        detail:
          `${reporting} / ${s.totalSites} sites remontés` +
          (estimated ? ` · ${estimated} estimé${estimated > 1 ? 's' : ''}` : ''),
      },
      {
        label: 'Charge moyenne du parc',
        value: s.averageLoadPercent === null ? '—' : `${number.format(s.averageLoadPercent)} %`,
        detail: `capacité ${number.format(s.totalCapacityKw)} kW`,
      },
      {
        label: 'Qualité des données',
        value: `${quality.good} / ${s.totalSites} OK`,
        detail: issues.length ? issues.join(' · ') : 'toutes les mesures sont complètes',
      },
    ];
  });

  /** The Mock API docs require flagging sites excluded from the total. */
  protected readonly missing = computed(() => {
    const s = this.summary();
    if (!s) {
      return [];
    }
    const names = new Map(s.sites.map((site) => [site.siteId, site.siteName]));
    return s.sitesWithoutData.map((id) => names.get(id) ?? id);
  });

  protected readonly parc = computed(() => parcSeries(this.series()));
  protected readonly chartLabels = computed(() =>
    this.parc().steps.map((ts) => hour.format(new Date(ts))),
  );
  protected readonly capacity = computed(() => this.summary()?.totalCapacityKw ?? null);

  protected readonly rows = computed(() => {
    const trends = trendsBySite(this.series());
    return sortByLoad(this.summary()?.sites ?? []).map((s) => ({
      ...s,
      consumption:
        s.currentConsumptionKw === null
          ? '—'
          : `${number.format(s.currentConsumptionKw)} kW${s.consumptionImputed ? ' (estimée)' : ''}`,
      barWidth: Math.min(s.loadPercent ?? 0, 100),
      quality: s.dataQuality ?? 'aucune',
      trend: trends.get(s.siteId) ?? [],
    }));
  });

  protected formatPercent(value: number): string {
    return `${number.format(value)} %`;
  }

  protected formatTime(timestamp: string): string {
    return hour.format(new Date(timestamp));
  }
}
