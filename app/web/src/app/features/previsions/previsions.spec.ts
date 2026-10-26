import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { of, throwError } from 'rxjs';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Previsions } from './previsions';

/**
 * Dans le mock, chaque site a une prévision horaire publiée jusqu'à l'heure en cours + 24 h (modèle
 * enervision-hourly-consumption, version 3), et des mesures sur les 12 dernières heures.
 */
describe('Previsions', () => {
  let fixture: ComponentFixture<Previsions>;
  let api: MockEnergyApi;

  async function render(site?: string): Promise<HTMLElement> {
    fixture = TestBed.createComponent(Previsions);
    if (site) {
      fixture.componentRef.setInput('site', site);
    }
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(el: HTMLElement, testId: string): string {
    return el.querySelector(`[data-testid="${testId}"]`)?.textContent?.trim() ?? '';
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [Previsions],
      providers: [
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: EnergyApi, useValue: api },
      ],
    }).compileComponents();
  });

  it('affiche par défaut le premier site, avec le pic prévu et le modèle', async () => {
    const el = await render();
    const select = el.querySelector('[data-testid="site"]') as HTMLSelectElement;
    expect(select.selectedOptions[0].textContent).toContain('Bureau Paris La Défense');
    expect(text(el, 'peak')).toMatch(/\d kW/);
    expect(text(el, 'peak')).toContain('% de la capacité');
    expect(text(el, 'energy')).toContain('kWh');
    expect(text(el, 'model')).toContain('enervision-hourly-consumption v3');
    expect(text(el, 'model')).toContain('série publiée à');
    expect(el.querySelector('canvas')).not.toBeNull();
  });

  it('affiche le site demandé dans l’URL', async () => {
    const el = await render('SITE002');
    const select = el.querySelector('[data-testid="site"]') as HTMLSelectElement;
    expect(select.selectedOptions[0].textContent).toContain('Usine Lyon Vénissieux');
    expect(el.querySelector('.meta')?.textContent).toContain('capacité 1000 kW');
  });

  it('change de site par l’URL', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = await render();
    const select = el.querySelector('[data-testid="site"]') as HTMLSelectElement;
    select.value = 'SITE005';
    select.dispatchEvent(new Event('change'));
    expect(navigate).toHaveBeenCalledWith(['/previsions'], { queryParams: { site: 'SITE005' } });
  });

  it('signale l’absence de prévision publiée', async () => {
    vi.spyOn(api, 'getPredictions').mockReturnValue(
      of({ siteId: 'SITE001', step: '1h', from: '', to: '', points: [] }),
    );
    const el = await render();
    expect(text(el, 'no-forecast')).toContain('Aucune prévision publiée');
    expect(el.querySelector('canvas')).toBeNull();
  });

  it('signale des prévisions indisponibles', async () => {
    vi.spyOn(api, 'getPredictions').mockReturnValue(throwError(() => new Error('500')));
    const el = await render();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Prévisions indisponibles');
  });

  it('garde la prévision quand les mesures sont indisponibles', async () => {
    vi.spyOn(api, 'getReadingSeries').mockReturnValue(throwError(() => new Error('500')));
    const el = await render();
    expect(el.querySelector('.chart [role="alert"]')?.textContent).toContain(
      'Mesures indisponibles',
    );
    expect(el.querySelector('canvas')).not.toBeNull();
  });
});
