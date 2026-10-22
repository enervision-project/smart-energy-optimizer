import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { EnergyApi } from './core/services/energy-api';
import { MockEnergyApi } from './core/services/mock-energy-api';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([]), { provide: EnergyApi, useClass: MockEnergyApi }],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render brand', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    const logo = compiled.querySelector('img.brand');
    expect(logo?.getAttribute('alt')).toBe('EnerVision');
    expect(logo?.getAttribute('src')).toBe('asset/logo_long.png');
  });

  it('propose une entrée Sites dans le menu latéral', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const links = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.sidebar a')];
    const sites = links.find((a) => a.textContent?.trim() === 'Sites');
    expect(sites?.getAttribute('href')).toBe('/sites');
  });

  it('affiche le nombre d’alertes de la dernière heure dans le menu', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const badge = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="alert-badge"]',
    );
    // le mock contient 7 alertes de moins d'une heure, dont 2 critiques
    expect(badge?.textContent?.trim()).toBe('7');
    expect(badge?.classList).toContain('critical');
  });
});
