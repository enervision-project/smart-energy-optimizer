import { CanActivateFn } from '@angular/router';

export const authGuard: CanActivateFn = () => {
  // paramètres méthode (mis ici cause linter): route, state
  return true;
};
