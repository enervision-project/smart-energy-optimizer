import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth-guard';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./features/login/login').then((m) => m.Login) },
  {
    path: '',
    canActivateChild: [authGuard],
    children: [
      { path: '', redirectTo: 'parc', pathMatch: 'full' },
      { path: 'parc', loadComponent: () => import('./features/parc/parc').then((m) => m.Parc) },
      { path: 'sites', loadComponent: () => import('./features/site/site').then((m) => m.Site) },
      {
        path: 'sites/:id',
        loadComponent: () => import('./features/site/site').then((m) => m.Site),
      },
      {
        path: 'previsions',
        loadComponent: () => import('./features/previsions/previsions').then((m) => m.Previsions),
      },
      {
        path: 'alertes',
        loadComponent: () => import('./features/alertes/alertes').then((m) => m.Alertes),
      },
      { path: '**', redirectTo: 'parc' },
    ],
  },
];
