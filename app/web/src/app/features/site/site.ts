import { Component, computed, inject, input } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { EnergyApi } from '../../core/services/energy-api';
import { ConsumptionChart } from '../../shared/components/consumption-chart/consumption-chart';
import { summarize } from './reading-summary';

const HOUR_MS = 3_600_000;
const WINDOW_HOURS = 48;

const SITE_TYPE_LABELS: Record<string, string> = {
  office: 'bureaux',
  factory: 'usine',
  datacenter: 'data center',
  retail: 'centre commercial',
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
  imports: [ConsumptionChart],
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

  protected readonly measures = rxResource({
    params: () => this.id(),
    stream: ({ params: id }) => this.api.getReadings(id, this.from, this.to),
    defaultValue: [],
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly profile = computed(() =>
    this.site.hasValue() ? this.site.value() : undefined,
  );
  private readonly readings = computed(() =>
    this.measures.hasValue() ? this.measures.value() : [],
  );

  protected readonly siteOptions = computed(() =>
    this.sites.hasValue() ? this.sites.value() : [],
  );

  protected selectSite(event: Event): void {
    const siteId = (event.target as HTMLSelectElement).value;
    this.router.navigate(['/sites', siteId]);
  }

  protected readonly siteTypeLabel = computed(() => {
    const type = this.profile()?.siteType ?? '';
    return SITE_TYPE_LABELS[type] ?? type;
  });

  protected readonly summary = computed(() => {
    const s = summarize(this.readings());
    return {
      energy: `${number.format(s.energyKwh / 1000)} MWh`,
      peak: s.peak
        ? `${number.format(s.peak.kw)} kW (${dateTime.format(new Date(s.peak.ts))})`
        : '—',
      availability: `${Math.round(s.availability * 100)} %`,
      quality: `${s.quality.good} good · ${s.quality.partial} partial · ${s.quality.degraded} degraded · ${s.quality.critical} critical`,
    };
  });

  protected readonly chartLabels = computed(() =>
    this.readings().map((r) => dateTime.format(new Date(r.ts))),
  );
  protected readonly chartValues = computed(() => this.readings().map((r) => r.consumption_kw));
}
