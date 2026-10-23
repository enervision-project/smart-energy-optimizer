import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { AUTH_ENABLED, LOGIN_URL } from '../../core/services/auth';
import { Login } from './login';

describe('Login', () => {
  let fixture: ComponentFixture<Login>;
  let backend: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  async function fill(email: string, password: string): Promise<void> {
    for (const [id, value] of [
      ['email', email],
      ['password', password],
    ]) {
      const input = el().querySelector(`[data-testid="${id}"]`) as HTMLInputElement;
      input.value = value;
      input.dispatchEvent(new Event('input'));
    }
    (el().querySelector('[data-testid="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
  }

  async function render(enabled = true, returnUrl?: string): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [Login],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AUTH_ENABLED, useValue: enabled },
      ],
    }).compileComponents();
    backend = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(Login);
    if (returnUrl) {
      fixture.componentRef.setInput('returnUrl', returnUrl);
    }
    await fixture.whenStable();
  }

  afterEach(() => {
    backend.verify();
    sessionStorage.clear();
  });

  it('se connecte puis revient à la page demandée', async () => {
    await render(true, '/alertes');
    await fill('jane@example.com', 'secret');

    backend
      .expectOne(LOGIN_URL)
      .flush({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 3600 });
    expect(navigate).toHaveBeenCalledWith('/alertes');
  });

  it('ignore une page de retour externe', async () => {
    await render(true, '//evil.example.com');
    await fill('jane@example.com', 'secret');

    backend
      .expectOne(LOGIN_URL)
      .flush({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 3600 });
    expect(navigate).toHaveBeenCalledWith('/parc');
  });

  it('signale des identifiants incorrects', async () => {
    await render();
    await fill('jane@example.com', 'wrong');

    backend.expectOne(LOGIN_URL).flush(null, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')?.textContent).toContain(
      'Email ou mot de passe incorrect',
    );
    expect(navigate).not.toHaveBeenCalled();
  });

  it('n’appelle pas l’API tant que le formulaire est invalide', async () => {
    await render();
    await fill('pas-un-email', '');
    backend.expectNone(LOGIN_URL);
    expect(el().textContent).toContain('Saisissez une adresse email valide');
  });

  it('n’affiche pas de formulaire quand la connexion est désactivée', async () => {
    await render(false);
    expect(el().querySelector('form')).toBeNull();
  });
});
