import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ALERT_REFRESH_MS, Alert } from '../../core/models/alert';
import { EnergyApi } from '../../core/services/energy-api';
import { MockEnergyApi } from '../../core/services/mock-energy-api';
import { Alertes } from './alertes';

/**
 * Le mock contient 9 alertes : 7 de moins d'une heure (2 critical, 1 high, 3 medium, 1 low),
 * puis une à 1 h 35 (SITE004) et une à 3 h (SITE001).
 */
const ALERT: Alert = {
  alertId: 'ALR-SITE002-1792667216',
  siteId: 'SITE002',
  siteName: 'Usine Lyon Vénissieux',
  timestamp: '2026-10-22T10:38:56Z',
  severity: 'high',
  type: 'spike',
  message: 'Pic de consommation détecté sur Usine Lyon Vénissieux',
  value: 912.5,
  threshold: 720,
  recent: true,
};

describe('Alertes', () => {
  let fixture: ComponentFixture<Alertes>;
  let api: MockEnergyApi;

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function rows(): HTMLElement[] {
    return [...el().querySelectorAll<HTMLElement>('[data-testid="alert-row"]')];
  }

  async function choose(testId: string, value: string): Promise<void> {
    const select = el().querySelector(`[data-testid="${testId}"]`) as HTMLSelectElement;
    select.value = value;
    select.dispatchEvent(new Event('change'));
    await fixture.whenStable();
  }

  /** Avec des timers simulés : avance le temps, puis laisse se terminer rendu et effets. */
  async function advance(ms: number): Promise<void> {
    fixture.detectChanges();
    await vi.advanceTimersByTimeAsync(ms);
    for (let i = 0; i < 3; i++) {
      fixture.detectChanges();
      await vi.advanceTimersByTimeAsync(0);
    }
  }

  async function render(): Promise<void> {
    fixture = TestBed.createComponent(Alertes);
    await fixture.whenStable();
  }

  beforeEach(async () => {
    api = new MockEnergyApi();
    await TestBed.configureTestingModule({
      imports: [Alertes],
      providers: [provideRouter([]), { provide: EnergyApi, useValue: api }],
    }).compileComponents();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('affiche les alertes de la dernière heure, de la plus récente à la plus ancienne', async () => {
    await render();
    expect(rows().length).toBe(7);
    expect(rows()[0].textContent).toContain('Data Center Marseille');
    expect(rows()[0].textContent).toContain('Critique');
    expect(rows()[0].textContent).toContain('Risque de surcharge sur Data Center Marseille');
    expect(el().querySelector('h2 .total')?.textContent).toContain('(7)');
  });

  it('affiche le nombre d’alertes récentes par sévérité', async () => {
    await render();
    const count = (sev: string) =>
      el().querySelector(`[data-testid="count-${sev}"] .count`)?.textContent?.trim();
    expect([count('critical'), count('high'), count('medium'), count('low')]).toEqual([
      '2',
      '1',
      '3',
      '1',
    ]);
  });

  it('élargit la période et grise les alertes de plus d’une heure', async () => {
    await render();
    await choose('period', '24');
    expect(rows().length).toBe(9);
    expect(rows().filter((r) => r.classList.contains('old')).length).toBe(2);
  });

  it('filtre par sévérité, type et site', async () => {
    await render();
    await choose('severity', 'critical');
    expect(rows().length).toBe(2);

    await choose('severity', '');
    await choose('type', 'threshold');
    expect(rows().length).toBe(2);

    await choose('site', 'SITE002');
    expect(rows().length).toBe(1);
    expect(rows()[0].textContent).toContain('Usine Lyon Vénissieux');
  });

  it('filtre sur la sévérité d’un compteur, puis retire le filtre au second clic', async () => {
    await render();
    const counter = el().querySelector('[data-testid="count-medium"]') as HTMLButtonElement;

    counter.click();
    await fixture.whenStable();
    expect(rows().length).toBe(3);
    expect(counter.getAttribute('aria-pressed')).toBe('true');

    counter.click();
    await fixture.whenStable();
    expect(rows().length).toBe(7);
  });

  it('filtre sur le site passé dans l’URL (?site=)', async () => {
    fixture = TestBed.createComponent(Alertes);
    fixture.componentRef.setInput('site', 'SITE002');
    await fixture.whenStable();
    expect(rows().length).toBe(2);
    const select = el().querySelector('[data-testid="site"]') as HTMLSelectElement;
    expect(select.selectedOptions[0].textContent).toContain('Usine Lyon Vénissieux');
  });

  it('lie chaque alerte à la page de son site', async () => {
    await render();
    expect(rows()[0].querySelector('a')?.getAttribute('href')).toBe('/sites/SITE003');
  });

  it('relit les alertes toutes les 30 secondes', async () => {
    vi.useFakeTimers();
    const getAlerts = vi.spyOn(api, 'getAlerts');
    // whenStable() attend des timers réels : avec des timers simulés, on avance le temps à la main
    fixture = TestBed.createComponent(Alertes);
    fixture.detectChanges();
    await vi.advanceTimersByTimeAsync(0);
    expect(getAlerts).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS);
    expect(getAlerts).toHaveBeenCalledTimes(2);
  });

  it('demande la page suivante, puis revient à la première quand un filtre change', async () => {
    const getAlerts = vi
      .spyOn(api, 'getAlerts')
      .mockImplementation((_filters, page, size) =>
        of({ content: [ALERT], page: { size, number: page, totalElements: 45, totalPages: 3 } }),
      );
    await render();
    expect(el().querySelector('.pager')?.textContent).toContain('Page 1 sur 3');

    const next = [...el().querySelectorAll<HTMLButtonElement>('.pager button')][1];
    next.click();
    await fixture.whenStable();
    expect(getAlerts).toHaveBeenLastCalledWith(expect.anything(), 1, 20);
    expect(el().querySelector('.pager')?.textContent).toContain('Page 2 sur 3');

    await choose('severity', 'high');
    expect(getAlerts).toHaveBeenLastCalledWith(expect.anything(), 0, 20);
  });

  it('reprend la mise à jour après une erreur', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'getAlerts').mockReturnValueOnce(throwError(() => new Error('503')));
    fixture = TestBed.createComponent(Alertes);
    await advance(0);
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('Alertes indisponibles');

    await advance(ALERT_REFRESH_MS);
    expect(el().querySelector('[role="alert"]')).toBeNull();
    expect(rows().length).toBe(7);
  });

  it('revient à la dernière page quand la page affichée n’existe plus', async () => {
    vi.useFakeTimers();
    let totalPages = 3;
    const getAlerts = vi.spyOn(api, 'getAlerts').mockImplementation((_filters, page, size) =>
      of({
        content: [ALERT],
        page: { size, number: page, totalElements: totalPages * size, totalPages },
      }),
    );
    fixture = TestBed.createComponent(Alertes);
    await advance(0);
    for (let i = 0; i < 2; i++) {
      [...el().querySelectorAll<HTMLButtonElement>('.pager button')][1].click();
      await advance(0);
    }
    expect(el().querySelector('.pager')?.textContent).toContain('Page 3 sur 3');

    // au rafraîchissement suivant, des alertes sont sorties de la période
    totalPages = 2;
    await advance(ALERT_REFRESH_MS);
    expect(getAlerts).toHaveBeenLastCalledWith(expect.anything(), 1, 20);
    expect(el().querySelector('.pager')?.textContent).toContain('Page 2 sur 2');
  });

  it('signale une API indisponible', async () => {
    vi.spyOn(api, 'getAlerts').mockReturnValue(throwError(() => new Error('503')));
    await render();
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('Alertes indisponibles');
  });
});
