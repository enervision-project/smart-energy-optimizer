import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Auth, AUTH_ENABLED, LOGIN_URL } from '../services/auth';
import { authInterceptor } from './auth-interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let auth: Auth;

  beforeEach(() => {
    sessionStorage.setItem(
      'enervision.session',
      JSON.stringify({ token: 'jwt', expiresAt: Date.now() + 60_000 }),
    );
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AUTH_ENABLED, useValue: true },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(Auth);
  });

  afterEach(() => {
    backend.verify();
    sessionStorage.clear();
  });

  it('ajoute le jeton aux appels à core-api', () => {
    http.get('/api/v1/sites').subscribe();
    expect(backend.expectOne('/api/v1/sites').request.headers.get('Authorization')).toBe(
      'Bearer jwt',
    );
  });

  it('n’envoie pas le jeton à la connexion ni hors de l’API', () => {
    http.post(LOGIN_URL, {}).subscribe();
    http.get('/asset/logo.png').subscribe();
    expect(backend.expectOne(LOGIN_URL).request.headers.has('Authorization')).toBe(false);
    expect(backend.expectOne('/asset/logo.png').request.headers.has('Authorization')).toBe(false);
  });

  it('ferme la session et renvoie vers la connexion sur une réponse 401', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    http.get('/api/v1/alerts').subscribe({ error: () => undefined });

    backend.expectOne('/api/v1/alerts').flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(auth.loggedIn()).toBe(false);
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/' } });
  });
});
