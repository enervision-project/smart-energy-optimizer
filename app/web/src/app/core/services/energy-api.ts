import { Observable } from 'rxjs';
import { Alert, AlertFilters, AlertSummary, Page } from '../models/alert';
import { ParcSummary } from '../models/parc-summary';
import { PredictionSeries } from '../models/prediction';
import { LatestReading, ReadingSeries, ReadingStep, ReadingSummary } from '../models/reading';
import { RecommendationResponse } from '../models/recommendation';
import { Site } from '../models/site';

/** Implementation (mock or HTTP) is chosen in `app.config.ts`. */
export abstract class EnergyApi {
  abstract getSites(): Observable<Site[]>;
  abstract getSite(siteId: string): Observable<Site>;
  abstract getReadingSeries(
    siteId: string,
    from: Date,
    to: Date,
    step: ReadingStep,
  ): Observable<ReadingSeries>;
  /** `null` when the site has no reading yet (204). */
  abstract getLatestReading(siteId: string): Observable<LatestReading | null>;
  abstract getReadingSummary(siteId: string, from: Date, to: Date): Observable<ReadingSummary>;
  abstract getAlerts(filters: AlertFilters, page: number, size: number): Observable<Page<Alert>>;
  abstract getAlertSummary(siteId?: string): Observable<AlertSummary>;
  abstract getRecommendations(siteId: string): Observable<RecommendationResponse | null>;
  abstract getParcSummary(): Observable<ParcSummary>;
  abstract getPredictions(siteId: string, from: Date, to: Date): Observable<PredictionSeries>;
}
