import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { throwError } from 'rxjs';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { MAX_ALERTS, Parc } from './parc';

/** In the mock, SITE003 has network loss, SITE002 a temperature sensor failure, and 7 alerts are recent. */
describe('Parc', () => {
  let fixture: ComponentFixture<Parc>;
  let api: MockEnergyApi;

  async function render(): Promise<HTMLElement> {
    fixture = TestBed.createComponent(Parc);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [Parc],
      providers: [
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: EnergyApi, useValue: api },
      ],
    }).compileComponents();
  });

  it('affiche les indicateurs du parc', async () => {
    const el = await render();
    const kpis = [...el.querySelectorAll('app-kpi-card')].map((k) => k.textContent);
    expect(kpis).toHaveLength(3);
    expect(kpis[0]).toContain('6 / 7 sites remontés');
    expect(kpis[1]).toMatch(/capacité 4\s130 kW/);
    expect(kpis[2]).toContain('5 / 7 OK');
    expect(kpis[2]).toContain('1 critical');
    expect(el.querySelector('[data-testid="updated"]')?.textContent).toContain('Mis à jour à');
  });

  it('signale le site exclu du total', async () => {
    const el = await render();
    expect(el.querySelector('[data-testid="missing"]')?.textContent).toContain(
      'Data Center Marseille est exclu',
    );
  });

  it('liste les 7 sites par charge décroissante, ceux sans valeur en dernier', async () => {
    const el = await render();
    const rows = [...el.querySelectorAll('tbody tr')];
    expect(rows).toHaveLength(7);
    const last = rows[6];
    expect(last.textContent).toContain('SITE003');
    expect(last.textContent).toContain('n/d');
    expect(last.querySelector('.badge')?.textContent).toBe('critical');

    const loads = rows
      .slice(0, 6)
      .map((r) => parseFloat(r.querySelector('.load')!.textContent!.replace(',', '.')));
    expect(loads).toEqual([...loads].sort((a, b) => b - a));
  });

  it('mène au détail de chaque site', async () => {
    const el = await render();
    const link = el.querySelector<HTMLAnchorElement>('tbody a[href="/sites/SITE001"]');
    expect(link?.textContent).toBe('Bureau Paris La Défense');
  });

  it('affiche les dernières alertes et le lien vers la page des alertes', async () => {
    const el = await render();
    expect(el.querySelectorAll('[data-testid="alert"]').length).toBe(MAX_ALERTS);
    expect(el.querySelector('#alerts-title')?.textContent).toContain('(7)');
    expect(el.querySelector('a.all-alerts')?.getAttribute('href')).toBe('/alertes');
  });

  it('signale une synthèse indisponible sans masquer la courbe', async () => {
    vi.spyOn(api, 'getParcSummary').mockReturnValue(throwError(() => new Error('500')));
    const el = await render();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain(
      'Synthèse du parc indisponible',
    );
    expect(el.querySelector('app-consumption-chart')).not.toBeNull();
  });

  it('signale des mesures indisponibles', async () => {
    vi.spyOn(api, 'getReadingSeries').mockReturnValue(throwError(() => new Error('500')));
    const el = await render();
    expect(el.querySelector('#chart-title + [role="alert"]')?.textContent).toContain(
      'Mesures indisponibles',
    );
  });
});
