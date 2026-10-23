import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  provideRouter,
  Router,
  RouterStateSnapshot,
  UrlTree,
} from '@angular/router';
import { AUTH_ENABLED } from '../services/auth';
import { authGuard } from './auth-guard';

describe('authGuard', () => {
  function run(url: string, enabled = true): boolean | UrlTree {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: AUTH_ENABLED, useValue: enabled }],
    });
    return TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url } as RouterStateSnapshot),
    ) as boolean | UrlTree;
  }

  afterEach(() => {
    sessionStorage.clear();
  });

  it('laisse passer un utilisateur connecté', () => {
    sessionStorage.setItem(
      'enervision.session',
      JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 60_000 }),
    );
    expect(run('/alertes')).toBe(true);
  });

  it('renvoie vers la connexion, puis vers la page demandée', () => {
    const result = run('/alertes');
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe(
      '/login?returnUrl=%2Falertes',
    );
  });

  it('laisse passer quand la connexion est désactivée (données factices)', () => {
    expect(run('/alertes', false)).toBe(true);
  });
});
