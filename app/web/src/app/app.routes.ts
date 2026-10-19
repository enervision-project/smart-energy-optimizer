import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'parc', pathMatch: 'full' },
  { path: 'parc', loadComponent: () => import('./features/parc/parc').then(m => m.Parc) },
  { path: 'sites/:id', loadComponent: () => import('./features/site/site').then(m => m.Site) },
  { path: 'previsions', loadComponent: () => import('./features/previsions/previsions').then(m => m.Previsions) },
  { path: 'alertes', loadComponent: () => import('./features/alertes/alertes').then(m => m.Alertes) },
  { path: '**', redirectTo: 'parc' },
];
