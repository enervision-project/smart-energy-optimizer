import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { RecommendationResponse } from '../../../core/models/recommendation';
import { EnergyApi } from '../../../core/services/energy-api';
import { MockEnergyApi } from '../../../core/services/mock-energy-api';
import { Recommendations } from './recommendations';

const MOCK_RECOMMENDATIONS: RecommendationResponse = {
  siteId: 'SITE001',
  timestamp: '2026-10-23T10:00:00Z',
  items: [
    {
      type: 'POWER_FACTOR',
      label: 'Facteur de puissance',
      value: 0.96,
      unit: '',
      quality: 'good',
      shortRecommendation: 'Votre facteur de puissance est excellent.',
      longRecommendation: 'Explication détaillée du facteur de puissance.',
    },
    {
      type: 'VOLTAGE',
      label: 'Voltage',
      value: 402.5,
      unit: 'V',
      quality: 'medium',
      shortRecommendation: 'Fluctuations de tension détectées.',
      longRecommendation: 'Explication détaillée de la tension.',
    },
    {
      type: 'LOAD_RATE',
      label: 'Taux de charge',
      value: null,
      unit: '%',
      quality: 'unknown',
      shortRecommendation: 'Données de mesure indisponibles pour ce paramètre.',
      longRecommendation: 'Capteur défaillant.',
    },
  ],
};

describe('Recommendations', () => {
  let fixture: ComponentFixture<Recommendations>;
  let api: MockEnergyApi;

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function items(): HTMLElement[] {
    return [...el().querySelectorAll<HTMLElement>('[data-testid="recommendation-item"]')];
  }

  async function render(siteId: string): Promise<void> {
    fixture = TestBed.createComponent(Recommendations);
    fixture.componentRef.setInput('siteId', siteId);
    await fixture.whenStable();
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [Recommendations],
      providers: [{ provide: EnergyApi, useValue: api }],
    }).compileComponents();
  });

  it('appelle l’API avec le siteId renseigné', async () => {
    const spy = vi.spyOn(api, 'getRecommendations').mockReturnValue(of(MOCK_RECOMMENDATIONS));
    await render('SITE001');
    expect(spy).toHaveBeenCalledWith('SITE001');
  });

  it('affiche un panneau par indicateur avec son label, sa valeur et la recommandation courte', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(of(MOCK_RECOMMENDATIONS));
    await render('SITE001');

    const cards = items();
    expect(cards.length).toBe(3);

    // Power factor (no unit)
    expect(cards[0].querySelector('[data-testid="recommendation-label"]')?.textContent).toContain(
      'Facteur de puissance',
    );
    expect(cards[0].querySelector('[data-testid="recommendation-value"]')?.textContent?.trim()).toBe(
      '0,96',
    );
    expect(cards[0].querySelector('[data-testid="recommendation-quality"]')?.textContent).toContain(
      'Optimale',
    );
    expect(cards[0].classList.contains('good')).toBe(true);
    expect(cards[0].querySelector('[data-testid="recommendation-short"]')?.textContent).toContain(
      'Votre facteur de puissance est excellent.',
    );

    // Voltage (V)
    expect(cards[1].querySelector('[data-testid="recommendation-label"]')?.textContent).toContain(
      'Voltage',
    );
    expect(cards[1].querySelector('[data-testid="recommendation-value"]')?.textContent?.trim()).toBe(
      '402,5 V',
    );
    expect(cards[1].querySelector('[data-testid="recommendation-quality"]')?.textContent).toContain(
      'À surveiller',
    );
    expect(cards[1].classList.contains('medium')).toBe(true);

    // Unknown / null value
    expect(cards[2].querySelector('[data-testid="recommendation-value"]')?.textContent?.trim()).toBe(
      '—',
    );
    expect(cards[2].querySelector('[data-testid="recommendation-quality"]')?.textContent).toContain(
      'Indisponible',
    );
    expect(cards[2].classList.contains('unknown')).toBe(true);
    expect(cards[2].querySelector('[data-testid="recommendation-short"]')?.textContent).toContain(
      'Données de mesure indisponibles',
    );
  });

  it('affiche la qualité brute si elle n’est pas reconnue', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(
      of({
        siteId: 'SITE001',
        timestamp: '2026-10-23T10:00:00Z',
        items: [
          {
            type: 'CUSTOM',
            label: 'Indicateur spécial',
            value: 12,
            unit: 'kW',
            quality: 'custom_quality',
            shortRecommendation: 'Recommandation test.',
            longRecommendation: 'Description test.',
          },
        ],
      }),
    );
    await render('SITE001');
    expect(
      el().querySelector('[data-testid="recommendation-quality"]')?.textContent?.trim(),
    ).toBe('custom_quality');
  });

  it('affiche et masque la recommandation longue au clic sur "Voir plus" / "Voir moins"', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(of(MOCK_RECOMMENDATIONS));
    await render('SITE001');

    const cards = items();
    const firstCard = cards[0];
    const toggleButton = firstCard.querySelector<HTMLButtonElement>('[data-testid="toggle-more"]');
    expect(toggleButton).not.toBeNull();
    expect(toggleButton?.textContent?.trim()).toBe('Voir plus');
    expect(firstCard.querySelector('[data-testid="recommendation-long"]')).toBeNull();

    toggleButton?.click();
    fixture.detectChanges();

    expect(toggleButton?.textContent?.trim()).toBe('Voir moins');
    const longRec = firstCard.querySelector('[data-testid="recommendation-long"]');
    expect(longRec).not.toBeNull();
    expect(longRec?.textContent).toContain('Explication détaillée du facteur de puissance.');

    toggleButton?.click();
    fixture.detectChanges();

    expect(toggleButton?.textContent?.trim()).toBe('Voir plus');
    expect(firstCard.querySelector('[data-testid="recommendation-long"]')).toBeNull();
  });

  it('signale l’absence de recommandations quand l’API renvoie une liste vide', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(
      of({ siteId: 'SITE001', timestamp: '2026-10-23T10:00:00Z', items: [] }),
    );
    await render('SITE001');
    expect(el().querySelector('.empty')?.textContent).toContain('Aucune recommandation');
  });

  it('signale l’absence de recommandations quand l’API renvoie null (204)', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(of(null));
    await render('SITE001');
    expect(el().querySelector('.empty')?.textContent).toContain('Aucune recommandation');
  });

  it('signale une erreur quand l’API échoue', async () => {
    vi.spyOn(api, 'getRecommendations').mockReturnValue(
      throwError(() => new Error('API indisponible')),
    );
    await render('SITE001');
    expect(el().querySelector('[role="alert"]')?.textContent).toContain(
      'Recommandations indisponibles',
    );
  });
});
