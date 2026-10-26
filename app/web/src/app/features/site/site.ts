import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ChartData, ChartOptions, TooltipItem } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { switchMap, timer } from 'rxjs';
import {
  LatestReading,
  READING_REFRESH_MS,
  READING_STEPS,
  ReadingPoint,
  ReadingStep,
  STALE_AFTER_SECONDS,
} from '../../core/models/reading';
import { reloadOnError } from '../../core/resources/reload-on-error';
import { EnergyApi } from '../../core/services/energy-api';
import { Recommendations } from './recommendations/recommendations';
import { noDataPlugin } from './no-data-plugin';
import { imputationLabel, nullReasonLabel, sensorStatuses } from './sensor-status';
import { SiteAlerts } from './site-alerts/site-alerts';

const HOUR_MS = 3_600_000;
/** core-api refuse le pas d'une minute au-delà de 48 h. */
const ONE_MINUTE_MAX_HOURS = 48;

const PERIODS = [
  { hours: 6, label: '6 h' },
  { hours: 24, label: '24 h' },
  { hours: 48, label: '48 h' },
  { hours: 168, label: '7 jours' },
];
const STEP_LABELS: Record<ReadingStep, string> = { '1m': '1 min', '15m': '15 min', '1h': '1 h' };

const SITE_TYPE_LABELS: Record<string, string> = {
  office: 'bureaux',
  factory: 'usine',
  datacenter: 'data center',
  retail: 'centre commercial',
  hospital: 'hôpital',
};

/** Cartes de la dernière mesure : champ, unité, capteur (`null_reasons`) et décimales. */
const MEASURES: {
  key: keyof LatestReading;
  label: string;
  unit: string;
  reason: string;
  digits: number;
}[] = [
  {
    key: 'consumptionKw',
    label: 'Consommation',
    unit: 'kW',
    reason: 'consumption_sensor_failure',
    digits: 1,
  },
  { key: 'voltageV', label: 'Tension', unit: 'V', reason: 'electrical_sensor_failure', digits: 1 },
  { key: 'currentA', label: 'Courant', unit: 'A', reason: 'electrical_sensor_failure', digits: 0 },
  {
    key: 'powerFactor',
    label: 'Facteur de puissance',
    unit: '',
    reason: 'electrical_sensor_failure',
    digits: 3,
  },
  {
    key: 'temperatureCelsius',
    label: 'Température',
    unit: '°C',
    reason: 'temperature_sensor_failure',
    digits: 1,
  },
  {
    key: 'humidityPercent',
    label: 'Humidité',
    unit: '%',
    reason: 'humidity_sensor_failure',
    digits: 0,
  },
];

const QUALITY_LABELS: Record<string, string> = {
  good: 'good',
  partial: 'partial',
  degraded: 'degraded',
  critical: 'critical',
  none: 'aucune mesure',
};

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const dateTime = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

function formatValue(value: number, digits: number): string {
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value);
}

@Component({
  imports: [BaseChartDirective, Recommendations, SiteAlerts],
  selector: 'app-site',
  styleUrl: './site.scss',
  templateUrl: './site.html',
})
export class Site {
  private readonly api = inject(EnergyApi);
  private readonly router = inject(Router);

  /** Paramètre `:id` de la route (via `withComponentInputBinding`) ; absent sur `/sites`. */
  readonly id = input<string>();

  protected readonly periods = PERIODS;
  protected readonly steps = READING_STEPS;
  protected readonly stepLabels = STEP_LABELS;
  protected readonly oneMinuteMaxHours = ONE_MINUTE_MAX_HOURS;

  protected readonly periodHours = signal(48);
  private readonly selectedStep = signal<ReadingStep>('15m');
  /** Le pas d'une minute repasse à 15 min quand la période dépasse 48 h. */
  protected readonly step = computed<ReadingStep>(() =>
    this.selectedStep() === '1m' && this.periodHours() > ONE_MINUTE_MAX_HOURS
      ? '15m'
      : this.selectedStep(),
  );
  protected readonly periodLabel = computed(
    () => PERIODS.find((p) => p.hours === this.periodHours())?.label ?? `${this.periodHours()} h`,
  );

  protected readonly sites = rxResource({
    stream: () => this.api.getSites(),
    defaultValue: [],
  });

  protected readonly site = rxResource({
    params: () => this.id(),
    stream: ({ params: id }) => this.api.getSite(id),
  });

  /** Dernière mesure, courbe et synthèse sont rafraîchies chaque minute ; la période glisse avec l'heure. */
  protected readonly latest = rxResource({
    params: () => this.id(),
    stream: ({ params: id }) =>
      timer(0, READING_REFRESH_MS).pipe(switchMap(() => this.api.getLatestReading(id))),
  });

  protected readonly series = rxResource({
    params: () => {
      const id = this.id();
      return id ? { id, hours: this.periodHours(), step: this.step() } : undefined;
    },
    stream: ({ params }) =>
      timer(0, READING_REFRESH_MS).pipe(
        switchMap(() => {
          const to = new Date();
          const from = new Date(to.getTime() - params.hours * HOUR_MS);
          return this.api.getReadingSeries(params.id, from, to, params.step);
        }),
      ),
  });

  protected readonly summary = rxResource({
    params: () => {
      const id = this.id();
      return id ? { id, hours: this.periodHours() } : undefined;
    },
    stream: ({ params }) =>
      timer(0, READING_REFRESH_MS).pipe(
        switchMap(() => {
          const to = new Date();
          return this.api.getReadingSummary(
            params.id,
            new Date(to.getTime() - params.hours * HOUR_MS),
            to,
          );
        }),
      ),
  });

  constructor() {
    // Sans site dans l'URL (`/sites`), le premier site visible est affiché ; `replaceUrl` évite qu'un retour
    // arrière ramène sur `/sites` et redirige de nouveau.
    effect(() => {
      const first = this.siteOptions()[0];
      if (!this.id() && first) {
        this.router.navigate(['/sites', first.siteId], { replaceUrl: true });
      }
    });
    reloadOnError(this.latest, READING_REFRESH_MS);
    reloadOnError(this.series, READING_REFRESH_MS);
    reloadOnError(this.summary, READING_REFRESH_MS);
  }

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly profile = computed(() =>
    this.site.hasValue() ? this.site.value() : undefined,
  );
  private readonly latestReading = computed(() =>
    this.latest.hasValue() ? this.latest.value() : null,
  );
  private readonly points = computed<ReadingPoint[]>(() =>
    this.series.hasValue() ? this.series.value().points : [],
  );

  protected readonly siteOptions = computed(() =>
    this.sites.hasValue() ? this.sites.value() : [],
  );

  protected readonly siteTypeLabel = computed(() => {
    const type = this.profile()?.siteType ?? '';
    return SITE_TYPE_LABELS[type] ?? type;
  });

  protected selectSite(event: Event): void {
    const siteId = (event.target as HTMLSelectElement).value;
    this.router.navigate(['/sites', siteId]);
  }

  protected selectPeriod(event: Event): void {
    this.periodHours.set(Number((event.target as HTMLSelectElement).value));
  }

  protected selectStep(event: Event): void {
    this.selectedStep.set((event.target as HTMLSelectElement).value as ReadingStep);
  }

  /** Âge et date de la dernière mesure ; `stale` quand la collecte semble arrêtée. */
  protected readonly freshness = computed(() => {
    const latest = this.latestReading();
    if (!latest) {
      return null;
    }
    return {
      at: dateTime.format(new Date(latest.ts)),
      age:
        latest.ageSeconds < 120
          ? `${latest.ageSeconds} s`
          : `${Math.round(latest.ageSeconds / 60)} min`,
      stale: latest.ageSeconds > STALE_AFTER_SECONDS,
    };
  });

  protected readonly cards = computed(() => {
    const latest = this.latestReading();
    const stale = !latest || latest.ageSeconds > STALE_AFTER_SECONDS;
    return MEASURES.map(({ key, label, unit, reason, digits }) => {
      const raw = latest ? (latest[key] as number | null) : null;
      const imputed = key === 'consumptionKw' ? (latest?.consumptionKwImputed ?? null) : null;
      const shown = raw ?? imputed;
      let status: string;
      let state: 'ok' | 'estimated' | 'failing' | 'stale';
      if (stale) {
        status = latest ? 'collecte arrêtée' : 'aucune mesure';
        state = 'stale';
      } else if (raw !== null) {
        status = 'mesure OK';
        state = 'ok';
      } else if (imputed !== null) {
        status = `valeur estimée (${imputationLabel(latest.imputationMethod ?? '')})`;
        state = 'estimated';
      } else {
        status = latest.nullReasons.includes('network_loss')
          ? 'perte réseau'
          : latest.nullReasons.includes(reason)
            ? 'capteur en panne'
            : 'valeur absente';
        state = 'failing';
      }
      return {
        key,
        label,
        value: shown === null ? '—' : `${formatValue(shown, digits)}${unit ? ' ' + unit : ''}`,
        status,
        state,
      };
    });
  });

  protected readonly sensors = computed(() => sensorStatuses(this.latestReading()));

  protected readonly qualityCells = computed(() =>
    this.points().map((p) => {
      const quality = p.minutesReceived === 0 ? 'none' : (p.dataQuality ?? 'none');
      return {
        ts: p.ts,
        quality,
        title: `${dateTime.format(new Date(p.ts))} : ${QUALITY_LABELS[quality]}`,
      };
    }),
  );

  protected readonly summaryView = computed(() => {
    if (!this.summary.hasValue()) {
      return null;
    }
    const s = this.summary.value();
    const energy =
      s.energyKwh === null
        ? '—'
        : s.energyKwh >= 1000
          ? `${number.format(s.energyKwh / 1000)} MWh`
          : `${number.format(s.energyKwh)} kWh`;
    return {
      energy,
      peak:
        s.peakKw === null || s.peakAt === null
          ? '—'
          : `${number.format(s.peakKw)} kW (${dateTime.format(new Date(s.peakAt))})`,
      availability:
        s.availabilityPercent === null ? '—' : `${number.format(s.availabilityPercent)} %`,
      hours: `${s.hoursWithData} / ${s.hoursExpected}`,
      imputed: `${s.minutesImputed} min`,
    };
  });

  /** Pas sans aucune mesure reçue, hachurés sur la courbe. */
  private readonly gapIndices = computed(() =>
    this.points().flatMap((p, i) => (p.minutesExpected > 0 && p.minutesReceived === 0 ? [i] : [])),
  );
  protected readonly chartPlugins = [noDataPlugin(() => this.gapIndices())];

  /**
   * Trois séries : consommation brute, valeur imputée (pointillés, seulement là où l'imputation change la
   * valeur, avec ses voisins pour relier la ligne) et capacité du site. Les pas sans valeur restent des trous.
   */
  protected readonly chartData = computed<ChartData<'line', (number | null)[], string>>(() => {
    const points = this.points();
    const capacity = this.profile()?.capacityKw ?? null;
    const changed = points.map(
      (p) => p.consumptionKwImputed !== null && p.consumptionKwImputed !== p.consumptionKw,
    );
    return {
      labels: points.map((p) => dateTime.format(new Date(p.ts))),
      datasets: [
        {
          label: 'Brute (mesurée)',
          data: points.map((p) => p.consumptionKw),
          borderColor: '#1f7a63',
          backgroundColor: '#1f7a63',
          borderWidth: 2,
          pointRadius: 0,
          spanGaps: false,
          order: 1,
        },
        {
          label: 'Imputée',
          data: points.map((p, i) =>
            changed[i] || changed[i - 1] || changed[i + 1] ? p.consumptionKwImputed : null,
          ),
          borderColor: '#1f2a37',
          backgroundColor: '#1f2a37',
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          spanGaps: false,
          order: 2,
        },
        {
          label: 'Capacité',
          data: points.map(() => capacity),
          borderColor: '#b23a48',
          backgroundColor: '#b23a48',
          borderDash: [2, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          order: 3,
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
      y: { beginAtZero: true, title: { display: true, text: 'kW' } },
    },
    plugins: {
      legend: { position: 'bottom' },
      tooltip: { callbacks: { afterBody: (items) => this.tooltipDetails(items) } },
    },
  };

  /** Survol : qualité, minutes reçues, méthode d'imputation et raisons des NULL du pas. */
  private tooltipDetails(items: TooltipItem<'line'>[]): string[] {
    const point = this.points()[items[0]?.dataIndex ?? -1];
    if (!point) {
      return [];
    }
    const lines = [
      `Qualité : ${QUALITY_LABELS[point.dataQuality ?? 'none']}`,
      `Minutes reçues : ${point.minutesReceived} / ${point.minutesExpected}`,
    ];
    if (point.minutesImputed) {
      lines.push(
        `Imputées : ${point.minutesImputed} min (${point.imputationMethods.map(imputationLabel).join(', ')})`,
      );
    }
    if (point.nullReasons.length) {
      lines.push(`NULL : ${point.nullReasons.map(nullReasonLabel).join(', ')}`);
    }
    return lines;
  }
}
