import { Component, computed, inject, input } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ChartData, ChartOptions } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { switchMap, timer } from 'rxjs';
import { READING_REFRESH_MS } from '../../core/models/reading';
import { reloadOnError } from '../../core/resources/reload-on-error';
import { EnergyApi } from '../../core/services/energy-api';
import { coveredUntil, forecastEnergy, forecastPeak, latestRun } from './forecast-summary';
import { nowLinePlugin } from './now-line-plugin';

const HOUR_MS = 3_600_000;
/** Mesuré sur les 12 dernières heures, prévision sur les 24 suivantes (maquette wf3, horizon H+24). */
export const PAST_HOURS = 12;
export const HORIZON_HOURS = 24;

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const hour = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
const dayHour = new Intl.DateTimeFormat('fr-FR', {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * Prévisions d'un site (wf3) : consommation mesurée des 12 dernières heures, prévision horaire des 24 suivantes
 * (avec la prévision qui avait été faite pour les heures passées, pour comparer), pic prévu et modèle utilisé.
 */
@Component({
  imports: [BaseChartDirective],
  selector: 'app-previsions',
  styleUrl: './previsions.scss',
  templateUrl: './previsions.html',
})
export class Previsions {
  private readonly api = inject(EnergyApi);
  private readonly router = inject(Router);

  /** Paramètre `?site=` (via `withComponentInputBinding`) ; le premier site visible par défaut. */
  readonly site = input<string>();

  protected readonly pastHours = PAST_HOURS;
  protected readonly horizonHours = HORIZON_HOURS;

  protected readonly sites = rxResource({
    stream: () => this.api.getSites(),
  });

  protected readonly siteOptions = computed(() =>
    this.sites.hasValue() ? this.sites.value() : [],
  );
  protected readonly siteId = computed(() => this.site() ?? this.siteOptions()[0]?.siteId);
  protected readonly selectedSite = computed(() =>
    this.siteOptions().find((s) => s.siteId === this.siteId()),
  );

  /** Mesuré et prévu sont relus chaque minute ; la fenêtre glisse avec l'heure. */
  protected readonly readings = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) =>
      timer(0, READING_REFRESH_MS).pipe(
        switchMap(() => {
          const now = Date.now();
          return this.api.getReadingSeries(
            siteId,
            new Date(now - PAST_HOURS * HOUR_MS),
            new Date(now),
            '1h',
          );
        }),
      ),
  });

  protected readonly predictions = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) =>
      timer(0, READING_REFRESH_MS).pipe(
        switchMap(() => {
          const now = Date.now();
          return this.api.getPredictions(
            siteId,
            new Date(now - PAST_HOURS * HOUR_MS),
            new Date(now + HORIZON_HOURS * HOUR_MS),
          );
        }),
      ),
  });

  constructor() {
    reloadOnError(this.readings, READING_REFRESH_MS);
    reloadOnError(this.predictions, READING_REFRESH_MS);
  }

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  private readonly points = computed(() =>
    this.predictions.hasValue() ? this.predictions.value().points : [],
  );
  private readonly measured = computed(() => {
    const series = this.readings.hasValue() ? this.readings.value().points : [];
    return new Map(series.map((p) => [Date.parse(p.ts), p.consumptionKw]));
  });

  protected selectSite(event: Event): void {
    const site = (event.target as HTMLSelectElement).value;
    void this.router.navigate(['/previsions'], { queryParams: { site } });
  }

  protected readonly hasForecast = computed(() =>
    this.points().some((p) => p.predictionKwh !== null),
  );

  protected readonly cards = computed(() => {
    const now = new Date();
    const points = this.points();
    const peak = forecastPeak(points, now);
    const energy = forecastEnergy(points, now);
    const until = coveredUntil(points);
    const run = latestRun(points);
    const capacity = this.selectedSite()?.capacityKw;
    return {
      peak: peak ? `${number.format(peak.kw)} kW` : '—',
      peakDetail: peak
        ? `${dayHour.format(new Date(peak.ts))}` +
          (capacity ? ` · ${number.format((100 * peak.kw) / capacity)} % de la capacité` : '')
        : 'aucune prévision à venir',
      energy: energy === null ? '—' : `${number.format(energy)} kWh`,
      until: until ? dayHour.format(new Date(until)) : '—',
      model: run ? `${run.modelName} v${run.modelVersion}` : '—',
      modelDetail: run ? `série publiée à ${hour.format(new Date(run.generatedAt))}` : '',
    };
  });

  /** Index fractionnaire de maintenant sur l'axe horaire, pour le trait « maintenant ». */
  private readonly nowIndex = computed(() => {
    const first = this.points()[0];
    if (!first) {
      return null;
    }
    return (Date.now() - Date.parse(first.ts)) / HOUR_MS;
  });
  protected readonly chartPlugins = [nowLinePlugin(() => this.nowIndex())];

  /**
   * Mesuré (trait plein), prévision (pointillés, heures passées comprises pour comparer) et capacité du site.
   * Le pic prévu est marqué d'un point.
   */
  protected readonly chartData = computed<ChartData<'line', (number | null)[], string>>(() => {
    const points = this.points();
    const measured = this.measured();
    const capacity = this.selectedSite()?.capacityKw ?? null;
    const peak = forecastPeak(points, new Date());
    return {
      labels: points.map((p) => hour.format(new Date(p.ts))),
      datasets: [
        {
          label: 'Mesuré',
          data: points.map((p) => measured.get(Date.parse(p.ts)) ?? null),
          borderColor: '#1f7a63',
          backgroundColor: '#1f7a63',
          borderWidth: 2,
          pointRadius: 0,
          spanGaps: false,
        },
        {
          label: 'Prévision',
          data: points.map((p) => p.predictionKwh),
          borderColor: '#1f2a37',
          backgroundColor: '#1f2a37',
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: points.map((p) => (peak && p.ts === peak.ts ? 5 : 0)),
          pointBackgroundColor: '#fff',
          spanGaps: false,
        },
        {
          label: 'Capacité',
          data: points.map(() => capacity),
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
      x: { ticks: { maxTicksLimit: 10, maxRotation: 0 } },
      y: { beginAtZero: true, title: { display: true, text: 'kW' } },
    },
    plugins: {
      legend: { position: 'bottom' },
    },
  };
}
