import { Component, computed, inject, input } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ChartData, ChartOptions } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { EnergyApi } from '../../core/services/energy-api';
import { isImputed, summarize } from './telemetry-summary';

const HOUR_MS = 3_600_000;
const WINDOW_HOURS = 48;

const SITE_TYPE_LABELS: Record<string, string> = {
  office: 'bureaux',
  factory: 'usine',
  data_center: 'data center',
  mall: 'centre commercial',
  hospital: 'hôpital',
};

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const dateTime = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

@Component({
  imports: [BaseChartDirective],
  selector: 'app-site',
  styleUrl: './site.scss',
  templateUrl: './site.html',
})
export class Site {
  private readonly api = inject(EnergyApi);
  private readonly router = inject(Router);

  /** Paramètre `:id` de la route (via `withComponentInputBinding`) ; absent sur `/sites`. */
  readonly id = input<string>();

  protected readonly sites = rxResource({
    stream: () => this.api.getSites(),
    defaultValue: [],
  });

  private readonly to = new Date(Math.floor(Date.now() / HOUR_MS) * HOUR_MS);
  private readonly from = new Date(this.to.getTime() - WINDOW_HOURS * HOUR_MS);

  protected readonly site = rxResource({
    params: () => this.id(),
    stream: ({ params: id }) => this.api.getSite(id),
  });

  protected readonly telemetry = rxResource({
    params: () => this.id(),
    stream: ({ params: id }) => this.api.getTelemetry(id, this.from, this.to),
    defaultValue: [],
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly profile = computed(() =>
    this.site.hasValue() ? this.site.value() : undefined,
  );
  private readonly readings = computed(() =>
    this.telemetry.hasValue() ? this.telemetry.value() : [],
  );

  protected readonly siteOptions = computed(() =>
    this.sites.hasValue() ? this.sites.value() : [],
  );

  protected selectSite(event: Event): void {
    const siteId = (event.target as HTMLSelectElement).value;
    this.router.navigate(['/sites', siteId]);
  }

  protected readonly siteTypeLabel = computed(() => {
    const type = this.profile()?.site_type ?? '';
    return SITE_TYPE_LABELS[type] ?? type;
  });

  protected readonly summary = computed(() => {
    const s = summarize(this.readings());
    return {
      energy: `${number.format(s.energyKwh / 1000)} MWh`,
      peak: s.peak
        ? `${number.format(s.peak.kwh)} kWh (${dateTime.format(new Date(s.peak.measured_at))})`
        : '—',
      availability: `${Math.round(s.availability * 100)} %`,
      imputed: `${s.imputedPoints} / ${s.totalPoints}`,
    };
  });

  /**
   * Trois séries : mesures brutes (trait plein), points imputés (pointillés, reliés aux mesures voisines)
   * et seuil `peak_consumption`. Les `null` restent des trous (`spanGaps: false`).
   */
  protected readonly chartData = computed<ChartData<'line', (number | null)[], string>>(() => {
    const readings = this.readings();
    const imputed = readings.map(isImputed);
    const values = readings.map((r) => r.consumption_kwh);
    const peak = this.profile()?.peak_consumption ?? null;

    return {
      labels: readings.map((r) => dateTime.format(new Date(r.measured_at))),
      datasets: [
        {
          label: 'Mesurée',
          data: values.map((v, i) => (imputed[i] ? null : v)),
          borderColor: '#1f7a63',
          backgroundColor: '#1f7a63',
          borderWidth: 2,
          pointRadius: 0,
          spanGaps: false,
        },
        {
          label: 'Imputée',
          data: values.map((v, i) => (imputed[i] || imputed[i - 1] || imputed[i + 1] ? v : null)),
          borderColor: '#d08c2b',
          backgroundColor: '#d08c2b',
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          spanGaps: false,
        },
        {
          label: 'Seuil contractuel',
          data: readings.map(() => peak),
          borderColor: '#b23a48',
          backgroundColor: '#b23a48',
          borderDash: [2, 4],
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    };
  });

  protected readonly chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: { ticks: { maxTicksLimit: 9, maxRotation: 0 } },
      y: { beginAtZero: true, title: { display: true, text: 'kWh / h' } },
    },
    plugins: {
      legend: { position: 'bottom' },
    },
  };
}
