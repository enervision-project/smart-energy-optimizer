import { Component, computed, effect, inject, input, linkedSignal, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { switchMap, tap, timer } from 'rxjs';
import {
  ALERT_REFRESH_MS,
  ALERT_SEVERITIES,
  ALERT_TYPES,
  AlertFilters,
  AlertSeverity,
  AlertType,
} from '../../core/models/alert';
import { reloadOnError } from '../../core/resources/reload-on-error';
import { EnergyApi } from '../../core/services/energy-api';
import { severityLabel, typeLabel } from './alert-labels';

const HOUR_MS = 3_600_000;
export const PAGE_SIZE = 20;

/** Périodes proposées, en heures ; 1 h = alertes récentes (fenêtre de l'API Mock). */
const PERIODS = [
  { hours: 1, label: 'Dernière heure' },
  { hours: 6, label: '6 heures' },
  { hours: 24, label: '24 heures' },
  { hours: 168, label: '7 jours' },
];

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});
const time = new Intl.DateTimeFormat('fr-FR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

@Component({
  imports: [RouterLink],
  selector: 'app-alertes',
  styleUrl: './alertes.scss',
  templateUrl: './alertes.html',
})
export class Alertes {
  private readonly api = inject(EnergyApi);

  protected readonly severities = ALERT_SEVERITIES;
  protected readonly types = ALERT_TYPES;
  protected readonly periods = PERIODS;
  protected readonly severityLabel = severityLabel;
  protected readonly typeLabel = typeLabel;

  /** Paramètre `?site=` de l'URL (lien « Voir toutes les alertes du site » de la vue site). */
  readonly site = input<string>();

  protected readonly siteId = linkedSignal(() => this.site() ?? '');
  protected readonly severity = signal<AlertSeverity | ''>('');
  protected readonly type = signal<AlertType | ''>('');
  protected readonly periodHours = signal(1);

  private readonly filters = computed(() => ({
    siteId: this.siteId(),
    severity: this.severity(),
    type: this.type(),
    periodHours: this.periodHours(),
  }));

  /** Revient à la première page à chaque changement de filtre. */
  protected readonly page = linkedSignal({ source: this.filters, computation: () => 0 });

  protected readonly lastUpdate = signal<Date | undefined>(undefined);

  protected readonly sites = rxResource({
    stream: () => this.api.getSites(),
    defaultValue: [],
  });

  /** Relancé toutes les 30 s ; la période glisse avec l'heure courante. */
  protected readonly alerts = rxResource({
    params: () => ({ filters: this.filters(), page: this.page() }),
    stream: ({ params }) =>
      timer(0, ALERT_REFRESH_MS).pipe(
        switchMap(() => this.api.getAlerts(toApiFilters(params.filters), params.page, PAGE_SIZE)),
        tap(() => this.lastUpdate.set(new Date())),
      ),
  });

  protected readonly summary = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) =>
      timer(0, ALERT_REFRESH_MS).pipe(
        switchMap(() => this.api.getAlertSummary(siteId || undefined)),
      ),
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly alertPage = computed(() =>
    this.alerts.hasValue() ? this.alerts.value() : undefined,
  );
  protected readonly counts = computed(() =>
    this.summary.hasValue() ? this.summary.value() : undefined,
  );
  protected readonly siteOptions = computed(() =>
    this.sites.hasValue() ? this.sites.value() : [],
  );

  protected readonly lastUpdateLabel = computed(() => {
    const date = this.lastUpdate();
    return date ? time.format(date) : '—';
  });

  constructor() {
    reloadOnError(this.alerts, ALERT_REFRESH_MS);
    reloadOnError(this.summary, ALERT_REFRESH_MS);

    // Des alertes sortent de la période à chaque rafraîchissement : la page affichée peut ne plus exister.
    effect(() => {
      const p = this.alertPage();
      if (p && p.page.number > 0 && p.page.number >= p.page.totalPages) {
        this.page.set(Math.max(0, p.page.totalPages - 1));
      }
    });
  }

  protected selectSite(event: Event): void {
    this.siteId.set((event.target as HTMLSelectElement).value);
  }

  protected selectSeverity(event: Event): void {
    this.severity.set((event.target as HTMLSelectElement).value as AlertSeverity | '');
  }

  protected selectType(event: Event): void {
    this.type.set((event.target as HTMLSelectElement).value as AlertType | '');
  }

  protected selectPeriod(event: Event): void {
    this.periodHours.set(Number((event.target as HTMLSelectElement).value));
  }

  /** Un clic sur un compteur filtre sur sa sévérité ; un second clic retire le filtre. */
  protected toggleSeverity(severity: AlertSeverity): void {
    this.severity.update((current) => (current === severity ? '' : severity));
  }

  protected previousPage(): void {
    this.page.update((p) => Math.max(0, p - 1));
  }

  protected nextPage(): void {
    this.page.update((p) => p + 1);
  }

  protected formatDate(timestamp: string): string {
    return dateTime.format(new Date(timestamp));
  }

  protected formatNumber(value: number | null): string {
    return value === null ? '—' : number.format(value);
  }
}

function toApiFilters(f: {
  siteId: string;
  severity: AlertSeverity | '';
  type: AlertType | '';
  periodHours: number;
}): AlertFilters {
  return {
    siteId: f.siteId || undefined,
    severity: f.severity ? [f.severity] : undefined,
    type: f.type ? [f.type] : undefined,
    from: new Date(Date.now() - f.periodHours * HOUR_MS),
  };
}
