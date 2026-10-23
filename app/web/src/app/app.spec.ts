import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { App } from './app';
import { AUTH_ENABLED } from './core/services/auth';
import { EnergyApi } from './core/services/energy-api';
import { MockEnergyApi } from './core/services/mock-energy-api';

describe('App', () => {
  let api: MockEnergyApi;

  function configure(authEnabled: boolean): void {
    api = new MockEnergyApi();
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EnergyApi, useValue: api },
        { provide: AUTH_ENABLED, useValue: authEnabled },
      ],
    });
  }

  afterEach(() => {
    sessionStorage.clear();
  });

  describe('sans connexion (données factices)', () => {
    beforeEach(() => configure(false));

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

    it('ne propose pas de déconnexion', async () => {
      const fixture = TestBed.createComponent(App);
      await fixture.whenStable();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('[data-testid="logout"]'),
      ).toBeNull();
    });
  });

  describe('avec connexion', () => {
    beforeEach(() => configure(true));

    it('n’interroge pas les alertes avant la connexion', async () => {
      const getAlertSummary = vi.spyOn(api, 'getAlertSummary');
      const fixture = TestBed.createComponent(App);
      await fixture.whenStable();
      expect(getAlertSummary).not.toHaveBeenCalled();
    });

    it('affiche l’utilisateur connecté et le déconnecte', async () => {
      sessionStorage.setItem(
        'enervision.session',
        JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 60_000 }),
      );
      const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
      const fixture = TestBed.createComponent(App);
      fixture.detectChanges();
      TestBed.inject(HttpTestingController)
        .expectOne('/api/v1/users/me')
        .flush({ id: '1', firstName: 'Jane', lastName: 'Doe', email: 'jane@example.com' });
      await fixture.whenStable();
      const el = fixture.nativeElement as HTMLElement;
      expect(el.querySelector('[data-testid="user-name"]')?.textContent).toContain('Jane Doe');

      (el.querySelector('[data-testid="logout"]') as HTMLButtonElement).click();
      await fixture.whenStable();
      expect(sessionStorage.getItem('enervision.session')).toBeNull();
      expect(navigate).toHaveBeenCalledWith(['/login']);
      expect(el.querySelector('[data-testid="logout"]')).toBeNull();
    });
  });
});
