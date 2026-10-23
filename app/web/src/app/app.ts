import { Component, computed, inject, signal } from '@angular/core';
import { rxResource, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { NgOptimizedImage } from '@angular/common';
import { filter, map, switchMap, timer } from 'rxjs';
import { ALERT_REFRESH_MS } from './core/models/alert';
import { reloadOnError } from './core/resources/reload-on-error';
import { Auth } from './core/services/auth';
import { EnergyApi } from './core/services/energy-api';

@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgOptimizedImage],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  private readonly api = inject(EnergyApi);
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);

  protected readonly title = signal('web');

  /** Page de connexion : affichée sans le menu. */
  protected readonly onLoginPage = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects.startsWith('/login')),
    ),
    { initialValue: false },
  );

  /** Utilisateur connecté, pour l'en-tête ; rien quand la connexion est désactivée (données factices). */
  protected readonly user = rxResource({
    params: () => (this.auth.enabled && this.auth.loggedIn()) || undefined,
    stream: () => this.auth.me(),
  });

  protected readonly userName = computed(() => {
    const user = this.user.hasValue() ? this.user.value() : undefined;
    return user ? `${user.firstName} ${user.lastName}` : undefined;
  });

  protected readonly canLogout = computed(() => this.auth.enabled && this.auth.loggedIn());

  /** Alertes de la dernière heure, pour le badge du menu ; relu toutes les 30 s, une fois connecté. */
  private readonly alertSummary = rxResource({
    params: () => this.auth.loggedIn() || undefined,
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

  constructor() {
    reloadOnError(this.alertSummary, ALERT_REFRESH_MS);
  }

  protected logout(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}
