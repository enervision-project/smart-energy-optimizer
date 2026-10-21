import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Site } from './site';

/** Dans le mock : SITE002 a 3 heures `degraded` et 4 `partial`, SITE003 est en perte réseau sur les 3 dernières heures. */
const SENSOR_FAILURE_SITE_ID = 'SITE002';
const NETWORK_LOSS_SITE_ID = 'SITE003';

describe('Site', () => {
  let fixture: ComponentFixture<Site>;

  async function render(id: string): Promise<HTMLElement> {
    fixture.componentRef.setInput('id', id);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Site],
      providers: [
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: EnergyApi, useClass: MockEnergyApi },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(Site);
  });

  it('invite à choisir un site quand aucun n’est sélectionné', async () => {
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('select option:not([disabled])').length).toBe(7);
    expect(el.querySelector('.hint')?.textContent).toContain('Sélectionnez un site');
  });

  it('présélectionne le site de l’URL dans la liste', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    const select = el.querySelector('select') as HTMLSelectElement;
    expect(select.selectedOptions[0].textContent).toContain('Usine Lyon Vénissieux');
  });

  it('navigue vers le site choisi', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = await render(SENSOR_FAILURE_SITE_ID);
    const select = el.querySelector('select') as HTMLSelectElement;
    select.value = 'SITE005';
    select.dispatchEvent(new Event('change'));
    expect(navigate).toHaveBeenCalledWith(['/sites', 'SITE005']);
  });

  it('affiche la ville et la capacité du site', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    expect(el.querySelector('.meta')?.textContent).toContain('Lyon, France · capacité 1000 kW');
  });

  it('compte les heures dégradées sans les filtrer', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    expect(el.querySelector('[data-testid="availability"]')?.textContent).toContain('94 %');
    expect(el.querySelector('[data-testid="quality"]')?.textContent).toContain(
      '41 good · 4 partial · 3 degraded · 0 critical',
    );
  });

  it('signale les heures en perte réseau comme critiques', async () => {
    const el = await render(NETWORK_LOSS_SITE_ID);
    expect(el.querySelector('[data-testid="availability"]')?.textContent).toContain('94 %');
    expect(el.querySelector('[data-testid="quality"]')?.textContent).toContain('3 critical');
  });

  it('signale un site inconnu', async () => {
    const el = await render('inconnu');
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Site introuvable');
  });
});
