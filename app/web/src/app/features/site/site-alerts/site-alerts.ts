import { Component, computed, inject, input } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { switchMap, timer } from 'rxjs';
import { ALERT_REFRESH_MS, ALERT_SEVERITIES } from '../../../core/models/alert';
import { reloadOnError } from '../../../core/resources/reload-on-error';
import { EnergyApi } from '../../../core/services/energy-api';
import { severityLabel, typeLabel } from '../../alertes/alert-labels';

const HOUR_MS = 3_600_000;
const WINDOW_HOURS = 24;
export const MAX_ALERTS = 10;

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

/** Alertes d'un site : compteurs de la dernière heure et dernières alertes sur 24 h, rafraîchis toutes les 30 s. */
@Component({
  imports: [RouterLink],
  selector: 'app-site-alerts',
  styleUrl: './site-alerts.scss',
  templateUrl: './site-alerts.html',
})
export class SiteAlerts {
  private readonly api = inject(EnergyApi);

  readonly siteId = input.required<string>();

  protected readonly severities = ALERT_SEVERITIES;
  protected readonly windowHours = WINDOW_HOURS;
  protected readonly severityLabel = severityLabel;
  protected readonly typeLabel = typeLabel;

  /** La fenêtre de 24 h glisse avec l'heure courante à chaque rafraîchissement. */
  protected readonly alerts = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) =>
      timer(0, ALERT_REFRESH_MS).pipe(
        switchMap(() =>
          this.api.getAlerts(
            { siteId, from: new Date(Date.now() - WINDOW_HOURS * HOUR_MS) },
            0,
            MAX_ALERTS,
          ),
        ),
      ),
  });

  protected readonly summary = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) =>
      timer(0, ALERT_REFRESH_MS).pipe(switchMap(() => this.api.getAlertSummary(siteId))),
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly alertPage = computed(() =>
    this.alerts.hasValue() ? this.alerts.value() : undefined,
  );
  protected readonly counts = computed(() =>
    this.summary.hasValue() ? this.summary.value() : undefined,
  );

  constructor() {
    reloadOnError(this.alerts, ALERT_REFRESH_MS);
    reloadOnError(this.summary, ALERT_REFRESH_MS);
  }

  protected formatDate(timestamp: string): string {
    return dateTime.format(new Date(timestamp));
  }

  protected formatNumber(value: number | null): string {
    return value === null ? '—' : number.format(value);
  }
}
