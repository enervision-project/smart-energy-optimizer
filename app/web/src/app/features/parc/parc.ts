import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EnergyApi } from '../../core/services/energy-api';
import { ConsumptionChart } from '../../shared/components/consumption-chart/consumption-chart';
import { KpiCard } from '../../shared/components/kpi-card/kpi-card';
import { Sparkline } from '../../shared/components/sparkline/sparkline';
import { missingSites, parcSeries, qualityCounts, sortByLoad, trendsBySite } from './parc-summary';

const HOUR_MS = 3_600_000;
const WINDOW_HOURS = 24;

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const hour = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });

@Component({
  imports: [RouterLink, KpiCard, ConsumptionChart, Sparkline],
  selector: 'app-parc',
  styleUrl: './parc.scss',
  templateUrl: './parc.html',
})
export class Parc {
  private readonly api = inject(EnergyApi);

  private readonly to = new Date(Math.floor(Date.now() / HOUR_MS) * HOUR_MS);
  private readonly from = new Date(this.to.getTime() - WINDOW_HOURS * HOUR_MS);

  protected readonly summaryResource = rxResource({
    stream: () => this.api.getParcSummary(),
  });

  protected readonly readingsResource = rxResource({
    stream: () => this.api.getParcReadings(this.from, this.to),
    defaultValue: [],
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  private readonly summary = computed(() =>
    this.summaryResource.hasValue() ? this.summaryResource.value() : undefined,
  );
  private readonly readings = computed(() =>
    this.readingsResource.hasValue() ? this.readingsResource.value() : [],
  );

  protected readonly kpis = computed(() => {
    const s = this.summary();
    if (!s) {
      return [];
    }
    const reporting = s.sites.length - missingSites(s.sites).length;
    const quality = qualityCounts(s.sites);
    const issues = (['partial', 'degraded', 'critical'] as const)
      .filter((q) => quality[q] > 0)
      .map((q) => `${quality[q]} ${q}`);
    return [
      {
        label: 'Consommation instantanée',
        value: `${number.format(s.total_consumption_kw)} kW`,
        detail: `${reporting} / ${s.total_sites} sites remontés`,
      },
      {
        label: 'Charge moyenne du parc',
        value: `${number.format(s.average_load_percent)} %`,
        detail: `capacité ${number.format(s.total_capacity_kw)} kW`,
      },
      {
        label: 'Qualité des données',
        value: `${quality.good} / ${s.total_sites} OK`,
        detail: issues.length ? issues.join(' · ') : 'toutes les mesures sont complètes',
      },
    ];
  });

  /** Noms des sites exclus du total : la doc de l'API Mock impose de le signaler. */
  protected readonly missing = computed(() =>
    missingSites(this.summary()?.sites ?? []).map((s) => s.site_name),
  );

  protected readonly series = computed(() => parcSeries(this.readings()));
  protected readonly chartLabels = computed(() =>
    this.series().hours.map((h) => hour.format(new Date(h))),
  );
  protected readonly capacity = computed(() => this.summary()?.total_capacity_kw ?? null);

  protected readonly rows = computed(() => {
    const trends = trendsBySite(this.readings());
    return sortByLoad(this.summary()?.sites ?? []).map((s) => ({
      ...s,
      consumption:
        s.current_consumption_kw === null ? '—' : `${number.format(s.current_consumption_kw)} kW`,
      barWidth: Math.min(s.load_percent ?? 0, 100),
      trend: trends.get(s.site_id) ?? [],
    }));
  });

  protected formatPercent(value: number): string {
    return `${number.format(value)} %`;
  }
}
