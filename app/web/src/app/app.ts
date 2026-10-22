import { Component, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { NgOptimizedImage } from '@angular/common';
import { switchMap, timer } from 'rxjs';
import { ALERT_REFRESH_MS } from './core/models/alert';
import { EnergyApi } from './core/services/energy-api';

@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgOptimizedImage],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  private readonly api = inject(EnergyApi);

  protected readonly title = signal('web');

  /** Alertes de la dernière heure, pour le badge du menu ; relu toutes les 30 s. */
  private readonly alertSummary = rxResource({
    stream: () => timer(0, ALERT_REFRESH_MS).pipe(switchMap(() => this.api.getAlertSummary())),
  });

  /** Nombre d'alertes récentes et sévérité la plus grave présente ; rien en cas d'échec. */
  protected readonly alertBadge = computed(() => {
    const summary = this.alertSummary.hasValue() ? this.alertSummary.value() : undefined;
    if (!summary || summary.total === 0) {
      return undefined;
    }
    const critical = summary.bySeverity.critical > 0;
    return { total: summary.total, critical };
  });
}
