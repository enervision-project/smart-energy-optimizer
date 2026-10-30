import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { EnergyApi } from '../../../core/services/energy-api';
import { MockEnergyApi } from '../../../core/services/mock-energy-api';
import { SiteAlerts } from './site-alerts';

describe('SiteAlerts', () => {
  let fixture: ComponentFixture<SiteAlerts>;
  let api: MockEnergyApi;

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function rows(): HTMLElement[] {
    return [...el().querySelectorAll<HTMLElement>('[data-testid="alert-row"]')];
  }

  function count(sev: string): string | undefined {
    return el().querySelector(`[data-testid="count-${sev}"] .count`)?.textContent?.trim();
  }

  async function render(siteId: string): Promise<void> {
    fixture = TestBed.createComponent(SiteAlerts);
    fixture.componentRef.setInput('siteId', siteId);
    await fixture.whenStable();
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [SiteAlerts],
      providers: [provideRouter([]), { provide: EnergyApi, useValue: api }],
    }).compileComponents();
  });

  it('affiche les alertes du site sur 24 h et grise celles de plus d’une heure', async () => {
    await render('SITE001');
    expect(rows().length).toBe(2);
    expect(rows()[0].textContent).toContain('Moyenne');
    expect(rows()[0].textContent).toContain('Seuil dépassé');
    expect(rows()[1].classList.contains('old')).toBe(true);
  });

  it('compte les alertes de la dernière heure du site par sévérité', async () => {
    await render('SITE001');
    expect([count('critical'), count('high'), count('medium'), count('low')]).toEqual([
      '0',
      '0',
      '1',
      '0',
    ]);
  });

  it('demande les alertes du site uniquement', async () => {
    const getAlerts = vi.spyOn(api, 'getAlerts');
    const getAlertSummary = vi.spyOn(api, 'getAlertSummary');
    await render('SITE004');
    expect(getAlerts.mock.calls[0][0].siteId).toBe('SITE004');
    expect(getAlertSummary).toHaveBeenCalledWith('SITE004');
  });

  it('lie vers la page des alertes filtrée sur le site', async () => {
    await render('SITE002');
    const link = el().querySelector('[data-testid="all-alerts"]');
    expect(link?.getAttribute('href')).toBe('/alertes?site=SITE002');
  });

  it('signale l’absence d’alerte', async () => {
    vi.spyOn(api, 'getAlerts').mockReturnValue(
      of({ content: [], page: { size: 10, number: 0, totalElements: 0, totalPages: 0 } }),
    );
    await render('SITE001');
    expect(el().querySelector('.empty')?.textContent).toContain('Aucune alerte');
  });

  it('signale une erreur de l’API', async () => {
    vi.spyOn(api, 'getAlerts').mockReturnValue(throwError(() => new Error('API injoignable')));
    await render('SITE001');
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('Alertes indisponibles');
  });
});
