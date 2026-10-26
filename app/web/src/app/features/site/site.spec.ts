import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { ChartOptions } from 'chart.js';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { of, throwError } from 'rxjs';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Site } from './site';

/**
 * Dans le mock : SITE002 a une panne du capteur de température sur les 20 dernières minutes et une coupure de
 * collecte d'une heure il y a 10 h ; SITE003 est en perte réseau sur les 3 dernières heures.
 */
const SENSOR_FAILURE_SITE_ID = 'SITE002';
const NETWORK_LOSS_SITE_ID = 'SITE003';

describe('Site', () => {
  let fixture: ComponentFixture<Site>;
  let api: MockEnergyApi;

  async function render(id: string): Promise<HTMLElement> {
    fixture.componentRef.setInput('id', id);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(el: HTMLElement, testId: string): string {
    return el.querySelector(`[data-testid="${testId}"]`)?.textContent?.trim() ?? '';
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [Site],
      providers: [
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: EnergyApi, useValue: api },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(Site);
  });

  it('affiche le premier site visible quand aucun n’est sélectionné', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('select option:not([disabled])').length).toBe(7);
    expect(navigate).toHaveBeenCalledWith(['/sites', 'SITE001'], { replaceUrl: true });
  });

  it('signale un compte sans site visible', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    vi.spyOn(api, 'getSites').mockReturnValue(of([]));
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).querySelector('.hint')?.textContent).toContain(
      'Aucun site',
    );
    expect(navigate).not.toHaveBeenCalled();
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

  it('affiche la dernière mesure et signale le capteur en panne', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    expect(text(el, 'measure-voltageV')).toContain('mesure OK');
    expect(text(el, 'measure-temperatureCelsius')).toContain('—');
    expect(text(el, 'measure-temperatureCelsius')).toContain('capteur en panne');
    expect(text(el, 'freshness')).toContain('il y a');
    expect(text(el, 'sensor-temperature')).toContain('En panne');
    expect(text(el, 'sensor-electrical')).toContain('OK');
  });

  it('en perte réseau, ne déclare que le réseau en panne', async () => {
    const el = await render(NETWORK_LOSS_SITE_ID);
    expect(text(el, 'measure-voltageV')).toContain('perte réseau');
    expect(text(el, 'sensor-network')).toContain('En panne');
    expect(text(el, 'sensor-consumption')).toContain('Inconnu');
  });

  it('montre la qualité de chaque pas, périodes sans mesure comprises', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    const band = el.querySelector('[data-testid="quality-band"]') as HTMLElement;
    // 48 h au pas de 15 min, la coupure d'une heure occupe au moins 3 pas entiers.
    expect(band.querySelectorAll('.cell').length).toBeGreaterThanOrEqual(192);
    expect(band.querySelectorAll('.cell.none').length).toBeGreaterThanOrEqual(3);
    expect(band.querySelectorAll('.cell.degraded').length).toBeGreaterThan(0);

    // 3 h de perte réseau : 12 pas de 15 min, 13 quand la panne n'est pas alignée sur le quart d'heure.
    const loss = await render(NETWORK_LOSS_SITE_ID);
    const critical = loss.querySelectorAll('[data-testid="quality-band"] .cell.critical').length;
    expect(critical).toBeGreaterThanOrEqual(12);
    expect(critical).toBeLessThanOrEqual(13);
  });

  it('détaille au survol la qualité, l’imputation et les valeurs manquantes du pas', async () => {
    await render(SENSOR_FAILURE_SITE_ID);
    const options = (fixture.componentInstance as unknown as { chartOptions: ChartOptions<'line'> })
      .chartOptions;
    const afterBody = options.plugins!.tooltip!.callbacks!.afterBody as unknown as (
      items: { dataIndex: number }[],
    ) => string[];
    const cells = [
      ...(fixture.nativeElement as HTMLElement).querySelectorAll('.quality-band .cell'),
    ];
    const degraded = cells.findIndex((c) => c.classList.contains('degraded'));

    const lines = afterBody([{ dataIndex: degraded }]);
    expect(lines[0]).toBe('Qualité : degraded');
    expect(lines.join(' ')).toContain('interpolation linéaire');
    expect(lines.join(' ')).toContain('capteur de consommation en panne');
    expect(afterBody([{ dataIndex: 10_000 }])).toEqual([]);
  });

  it('affiche la synthèse de la période', async () => {
    const el = await render(NETWORK_LOSS_SITE_ID);
    expect(el.querySelector('#summary-title')?.textContent).toContain('Synthèse 48 h');
    expect(text(el, 'energy')).toContain('MWh');
    expect(text(el, 'availability')).toMatch(/^9\d(,\d)? %$/);
    expect(text(el, 'imputed')).toBe('15 min');
  });

  it('interdit le pas d’une minute au-delà de 48 h', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    const period = el.querySelector('[data-testid="period"]') as HTMLSelectElement;
    period.value = '168';
    period.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    const step = el.querySelector('[data-testid="step"]') as HTMLSelectElement;
    expect((step.querySelector('option[value="1m"]') as HTMLOptionElement).disabled).toBe(true);
    expect(el.querySelector('#summary-title')?.textContent).toContain('Synthèse 7 jours');
  });

  it('signale des mesures indisponibles', async () => {
    vi.spyOn(api, 'getReadingSeries').mockReturnValue(throwError(() => new Error('500')));
    const el = await render(SENSOR_FAILURE_SITE_ID);
    expect(el.querySelector('.chart [role="alert"]')?.textContent).toContain(
      'Mesures indisponibles',
    );
  });

  it('affiche le panneau de recommandations au-dessus du tableau de bord', async () => {
    const el = await render(SENSOR_FAILURE_SITE_ID);
    expect(el.querySelector('app-recommendations')).not.toBeNull();
  });

  it('signale un site inconnu', async () => {
    const el = await render('inconnu');
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Site introuvable');
  });
});
