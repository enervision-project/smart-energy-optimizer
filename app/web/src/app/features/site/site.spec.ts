import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Site } from './site';

/** Usine en perte réseau dans le mock : 3 points manquants et 4 imputés sur 48. */
const DEGRADED_SITE_ID = '00000000-0000-4000-8000-000000000003';

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
    const el = await render(DEGRADED_SITE_ID);
    const select = el.querySelector('select') as HTMLSelectElement;
    expect(select.selectedOptions[0].textContent).toContain('Usine Lyon Vénissieux');
  });

  it('navigue vers le site choisi', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = await render(DEGRADED_SITE_ID);
    const select = el.querySelector('select') as HTMLSelectElement;
    select.value = '00000000-0000-4000-8000-000000000005';
    select.dispatchEvent(new Event('change'));
    expect(navigate).toHaveBeenCalledWith(['/sites', '00000000-0000-4000-8000-000000000005']);
  });

  it('compte les points manquants et imputés sans les filtrer', async () => {
    const el = await render(DEGRADED_SITE_ID);
    expect(el.querySelector('[data-testid="availability"]')?.textContent).toContain('94 %');
    expect(el.querySelector('[data-testid="imputed"]')?.textContent).toContain('4 / 48');
  });

  it('signale un site inconnu', async () => {
    const el = await render('inconnu');
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Site introuvable');
  });
});
