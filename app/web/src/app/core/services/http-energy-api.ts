import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { Observable } from 'rxjs';
import { Alert, AlertFilters, AlertSummary, Page } from '../models/alert';
import { ParcSummary } from '../models/parc-summary';
import { PredictionSeries } from '../models/prediction';
import { LatestReading, ReadingSeries, ReadingStep, ReadingSummary } from '../models/reading';
import { RecommendationResponse } from '../models/recommendation';
import { Site } from '../models/site';
import { API_BASE_URL as BASE_URL } from './api';
import { EnergyApi } from './energy-api';

@Service()
export class HttpEnergyApi extends EnergyApi {
  private readonly http = inject(HttpClient);

  getSites(): Observable<Site[]> {
    return this.http.get<Site[]>(`${BASE_URL}/sites`);
  }

  getSite(siteId: string): Observable<Site> {
    return this.http.get<Site>(`${BASE_URL}/sites/${siteId}`);
  }

  /** Routes de core-api (module telemetry). */
  getReadingSeries(
    siteId: string,
    from: Date,
    to: Date,
    step: ReadingStep,
  ): Observable<ReadingSeries> {
    return this.http.get<ReadingSeries>(`${BASE_URL}/sites/${siteId}/readings`, {
      params: { from: from.toISOString(), to: to.toISOString(), step },
    });
  }

  getLatestReading(siteId: string): Observable<LatestReading | null> {
    return this.http.get<LatestReading | null>(`${BASE_URL}/sites/${siteId}/readings/latest`);
  }

  getReadingSummary(siteId: string, from: Date, to: Date): Observable<ReadingSummary> {
    return this.http.get<ReadingSummary>(`${BASE_URL}/sites/${siteId}/readings/summary`, {
      params: { from: from.toISOString(), to: to.toISOString() },
    });
  }

  /** Route de core-api (module diagnostic). */
  getAlerts(filters: AlertFilters, page: number, size: number): Observable<Page<Alert>> {
    let params = new HttpParams().set('page', page).set('size', size);
    if (filters.siteId) {
      params = params.set('siteId', filters.siteId);
    }
    if (filters.severity?.length) {
      params = params.set('severity', filters.severity.join(','));
    }
    if (filters.type?.length) {
      params = params.set('type', filters.type.join(','));
    }
    if (filters.from) {
      params = params.set('from', filters.from.toISOString());
    }
    if (filters.to) {
      params = params.set('to', filters.to.toISOString());
    }
    return this.http.get<Page<Alert>>(`${BASE_URL}/alerts`, { params });
  }

  /** Route de core-api (module telemetry). */
  getParcSummary(): Observable<ParcSummary> {
    return this.http.get<ParcSummary>(`${BASE_URL}/stats/summary`);
  }

  getPredictions(siteId: string, from: Date, to: Date): Observable<PredictionSeries> {
    return this.http.get<PredictionSeries>(`${BASE_URL}/sites/${siteId}/predictions`, {
      params: { from: from.toISOString(), to: to.toISOString() },
    });
  }

  getAlertSummary(siteId?: string): Observable<AlertSummary> {
    return this.http.get<AlertSummary>(`${BASE_URL}/alerts/summary`, {
      params: siteId ? { siteId } : {},
    });
  }

  getRecommendations(siteId: string): Observable<RecommendationResponse | null> {
    return this.http.get<RecommendationResponse | null>(`${BASE_URL}/recommendations/${siteId}`);
  }
}
