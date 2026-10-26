import { Component, computed, inject, input, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { of } from 'rxjs';
import { EnergyApi } from '../../../core/services/energy-api';

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });

const QUALITY_LABELS: Record<string, string> = {
  good: 'Optimale',
  medium: 'À surveiller',
  bad: 'Critique',
  unknown: 'Indisponible',
};

/**
 * Recommandations d'un site calculées en temps réel par core-api à partir de sa dernière mesure.
 * Affiche un panneau par indicateur (facteur de puissance, tension, taux de charge) avec sa qualité.
 */
@Component({
  imports: [],
  selector: 'app-recommendations',
  styleUrl: './recommendations.scss',
  templateUrl: './recommendations.html',
})
export class Recommendations {
  private readonly api = inject(EnergyApi);

  readonly siteId = input.required<string>();

  protected readonly recommendations = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) => (siteId ? this.api.getRecommendations(siteId) : of(null)),
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly response = computed(() =>
    this.recommendations.hasValue() ? this.recommendations.value() : undefined,
  );

  protected readonly expandedItems = signal<Record<string, boolean>>({});

  protected toggleExpand(type: string): void {
    this.expandedItems.update((state) => ({
      ...state,
      [type]: !state[type],
    }));
  }

  protected isExpanded(type: string): boolean {
    return this.expandedItems()[type];
  }

  protected formatValue(value: number | null, unit: string): string {
    if (value === null) {
      return '—';
    }
    const formatted = number.format(value);
    return unit ? `${formatted} ${unit}` : formatted;
  }

  protected qualityLabel(quality: string): string {
    return QUALITY_LABELS[quality] ?? quality;
  }
}
