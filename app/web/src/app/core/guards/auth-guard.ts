import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Auth } from '../services/auth';

/** Pages réservées aux utilisateurs connectés : sinon, connexion puis retour à la page demandée. */
export const authGuard: CanActivateFn = (_route, state) =>
  inject(Auth).isLoggedIn() ||
  inject(Router).createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
