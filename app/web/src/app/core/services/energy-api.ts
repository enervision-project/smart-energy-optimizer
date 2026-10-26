import { Observable } from 'rxjs';
import { Alert, AlertFilters, AlertSummary, Page } from '../models/alert';
import { ParcSummary } from '../models/parc-summary';
import { LatestReading, ReadingSeries, ReadingStep, ReadingSummary } from '../models/reading';
import { RecommendationResponse } from '../models/recommendation';
import { Site } from '../models/site';

/** Seul point d'accès aux données pour les pages : l'implémentation (mock ou HTTP) est choisie dans `app.config.ts`. */
export abstract class EnergyApi {
  abstract getSites(): Observable<Site[]>;
  abstract getSite(siteId: string): Observable<Site>;
  /** Courbe d'un site, un point par pas ; `from` et `to` sont alignés sur le pas par core-api. */
  abstract getReadingSeries(
    siteId: string,
    from: Date,
    to: Date,
    step: ReadingStep,
  ): Observable<ReadingSeries>;
  /** Dernière mesure du site, `null` s'il n'en a encore aucune (204). */
  abstract getLatestReading(siteId: string): Observable<LatestReading | null>;
  /** Énergie, pic et disponibilité du site sur `[from, to)`. */
  abstract getReadingSummary(siteId: string, from: Date, to: Date): Observable<ReadingSummary>;
  /** Alertes des sites visibles, de la plus récente à la plus ancienne (`page` commence à 0). */
  abstract getAlerts(filters: AlertFilters, page: number, size: number): Observable<Page<Alert>>;
  /** Nombre d'alertes de la dernière heure par sévérité, pour tous les sites visibles ou un seul. */
  abstract getAlertSummary(siteId?: string): Observable<AlertSummary>;
  /** Recommandations d'efficacité et de santé électrique pour un site. */
  abstract getRecommendations(siteId: string): Observable<RecommendationResponse | null>;
  /** Consommation actuelle des sites visibles et sites sans mesure récente. */
  abstract getParcSummary(): Observable<ParcSummary>;
}
