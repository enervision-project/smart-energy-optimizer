import { HttpClient } from '@angular/common/http';
import { computed, inject, InjectionToken, Service, signal } from '@angular/core';
import { map, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { TokenResponse, User } from '../models/auth';
import { API_BASE_URL } from './api';

export const LOGIN_URL = `${API_BASE_URL}/auth/login`;

/** False on mock data (`useMock`): no back end, so no login. */
export const AUTH_ENABLED = new InjectionToken<boolean>('AUTH_ENABLED', {
  factory: () => !environment.useMock,
});

const STORAGE_KEY = 'enervision.session';

interface Session {
  token: string;
  expiresAt: number;
}

/** JWT kept in `sessionStorage`: survives a reload, lost when the tab closes. */
@Service()
export class Auth {
  private readonly http = inject(HttpClient);

  readonly enabled = inject(AUTH_ENABLED);

  private readonly session = signal<Session | undefined>(readSession());

  readonly loggedIn = computed(() => !this.enabled || this.session() !== undefined);

  login(email: string, password: string): Observable<void> {
    return this.http.post<TokenResponse>(LOGIN_URL, { email, password }).pipe(
      map((response) =>
        this.store({
          token: response.accessToken,
          expiresAt: Date.now() + response.expiresIn * 1000,
        }),
      ),
    );
  }

  logout(): void {
    this.store(undefined);
  }

  token(): string | undefined {
    const session = this.session();
    if (session && session.expiresAt <= Date.now()) {
      this.logout();
      return undefined;
    }
    return session?.token;
  }

  /** Unlike `loggedIn`, also checks the token expiry. */
  isLoggedIn(): boolean {
    return !this.enabled || this.token() !== undefined;
  }

  me(): Observable<User> {
    return this.http.get<User>(`${API_BASE_URL}/users/me`);
  }

  private store(session: Session | undefined): void {
    this.session.set(session);
    try {
      if (session) {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // storage unavailable (strict private browsing): the session stays in memory
    }
  }
}

function readSession(): Session | undefined {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const session = raw ? (JSON.parse(raw) as Session) : undefined;
    return session && session.expiresAt > Date.now() ? session : undefined;
  } catch {
    return undefined;
  }
}
