import { Observable } from 'rxjs';
import { Alert, AlertFilters, AlertSummary, Page } from '../models/alert';
import { ParcSummary } from '../models/parc-summary';
import { Reading } from '../models/reading';
import { Site } from '../models/site';

/** Seul point d'accès aux données pour les pages : l'implémentation (mock ou HTTP) est choisie dans `app.config.ts`. */
export abstract class EnergyApi {
  abstract getSites(): Observable<Site[]>;
  abstract getSite(siteId: string): Observable<Site>;
  /** Mesures horaires d'un site de `from` (inclus) à `to` (exclu). */
  abstract getReadings(siteId: string, from: Date, to: Date): Observable<Reading[]>;
  /** Alertes des sites visibles, de la plus récente à la plus ancienne (`page` commence à 0). */
  abstract getAlerts(filters: AlertFilters, page: number, size: number): Observable<Page<Alert>>;
  /** Nombre d'alertes de la dernière heure par sévérité, pour tous les sites visibles ou un seul. */
  abstract getAlertSummary(siteId?: string): Observable<AlertSummary>;
  /** Mesures horaires de tous les sites de `from` (inclus) à `to` (exclu). */
  abstract getParcReadings(from: Date, to: Date): Observable<Reading[]>;
  abstract getParcSummary(): Observable<ParcSummary>;
}
