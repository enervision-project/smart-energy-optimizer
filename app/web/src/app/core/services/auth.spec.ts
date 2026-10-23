import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Auth, AUTH_ENABLED, LOGIN_URL } from './auth';

describe('Auth', () => {
  let http: HttpTestingController;

  function create(): Auth {
    return TestBed.inject(Auth);
  }

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AUTH_ENABLED, useValue: true },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('ouvre une session avec le jeton renvoyé par l’API et la garde dans le sessionStorage', () => {
    const auth = create();
    auth.login('jane@example.com', 'secret').subscribe();

    const req = http.expectOne(LOGIN_URL);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'jane@example.com', password: 'secret' });
    req.flush({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 3600 });

    expect(auth.loggedIn()).toBe(true);
    expect(auth.token()).toBe('jwt');
    expect(sessionStorage.getItem('enervision.session')).toContain('jwt');
  });

  it('reprend la session après un rechargement de la page', () => {
    sessionStorage.setItem(
      'enervision.session',
      JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 60_000 }),
    );
    expect(create().token()).toBe('jwt');
  });

  it('ferme la session quand le jeton a expiré', () => {
    vi.useFakeTimers();
    const auth = create();
    auth.login('jane@example.com', 'secret').subscribe();
    http.expectOne(LOGIN_URL).flush({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 60 });

    vi.advanceTimersByTime(61_000);
    expect(auth.isLoggedIn()).toBe(false);
    expect(auth.loggedIn()).toBe(false);
    expect(sessionStorage.getItem('enervision.session')).toBeNull();
  });

  it('se déconnecte', () => {
    sessionStorage.setItem(
      'enervision.session',
      JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 60_000 }),
    );
    const auth = create();
    auth.logout();
    expect(auth.token()).toBeUndefined();
    expect(sessionStorage.getItem('enervision.session')).toBeNull();
  });
});
