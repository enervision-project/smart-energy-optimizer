import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { Observable } from 'rxjs';
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
}
