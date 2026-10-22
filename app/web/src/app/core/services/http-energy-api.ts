import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { Observable } from 'rxjs';
import { Alert, AlertFilters, AlertSummary, Page } from '../models/alert';
import { Reading } from '../models/reading';
import { Site } from '../models/site';
import { EnergyApi } from './energy-api';

/** URL provisoires, calquées sur l'API Mock : les routes de l'API Spring Boot restent à fixer avec l'équipe back. */
const BASE_URL = '/api/v1';

@Service()
export class HttpEnergyApi extends EnergyApi {
  private readonly http = inject(HttpClient);

  getSites(): Observable<Site[]> {
    return this.http.get<Site[]>(`${BASE_URL}/sites`);
  }

  getSite(siteId: string): Observable<Site> {
    return this.http.get<Site>(`${BASE_URL}/sites/${siteId}`);
  }

  getReadings(siteId: string, from: Date, to: Date): Observable<Reading[]> {
    return this.http.get<Reading[]>(`${BASE_URL}/readings`, {
      params: { site_id: siteId, start_time: from.toISOString(), end_time: to.toISOString() },
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

  getAlertSummary(siteId?: string): Observable<AlertSummary> {
    return this.http.get<AlertSummary>(`${BASE_URL}/alerts/summary`, {
      params: siteId ? { siteId } : {},
    });
  }
}
