import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { API_BASE_URL } from '../services/api';
import { Auth, LOGIN_URL } from '../services/auth';

/**
 * Ajoute le jeton aux appels à core-api. Une réponse 401 (jeton expiré ou révoqué) ferme la session
 * et renvoie vers la page de connexion, qui ramènera ensuite à la page courante.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE_URL) || req.url === LOGIN_URL) {
    return next(req);
  }
  const auth = inject(Auth);
  const router = inject(Router);
  const token = auth.token();
  const request = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(request).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401 && auth.enabled) {
        auth.logout();
        if (!router.url.startsWith('/login')) {
          void router.navigate(['/login'], { queryParams: { returnUrl: router.url } });
        }
      }
      return throwError(() => error);
    }),
  );
};
