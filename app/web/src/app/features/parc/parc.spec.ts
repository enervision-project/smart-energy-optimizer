import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Parc } from './parc';

/** Dans le mock, SITE003 (Data Center Marseille) n'a plus de mesure depuis 3 heures. */
describe('Parc', () => {
  let el: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Parc],
      providers: [
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: EnergyApi, useClass: MockEnergyApi },
      ],
    }).compileComponents();

    const fixture: ComponentFixture<Parc> = TestBed.createComponent(Parc);
    await fixture.whenStable();
    el = fixture.nativeElement as HTMLElement;
  });

  it('affiche les indicateurs du parc', () => {
    const kpis = [...el.querySelectorAll('app-kpi-card')].map((k) => k.textContent);
    expect(kpis).toHaveLength(3);
    expect(kpis[0]).toContain('6 / 7 sites remontés');
    expect(kpis[1]).toMatch(/capacité 4\s130 kW/);
    expect(kpis[2]).toContain('6 / 7 OK');
    expect(kpis[2]).toContain('1 critical');
  });

  it('signale le site exclu du total', () => {
    expect(el.querySelector('.warning')?.textContent).toContain('Data Center Marseille est exclu');
  });

  it('liste les 7 sites par charge décroissante, ceux sans mesure en dernier', () => {
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

  it('mène au détail de chaque site', () => {
    const link = el.querySelector<HTMLAnchorElement>('tbody a[href="/sites/SITE001"]');
    expect(link?.textContent).toBe('Bureau Paris La Défense');
  });
});
