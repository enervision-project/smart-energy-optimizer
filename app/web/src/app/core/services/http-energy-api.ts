import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { Observable } from 'rxjs';
import { SiteProfile } from '../models/site-profile';
import { Telemetry } from '../models/telemetry';
import { EnergyApi } from './energy-api';

/** URL provisoires : les routes de l'API Spring Boot restent à fixer avec l'équipe back. */
const BASE_URL = '/api';

@Service()
export class HttpEnergyApi extends EnergyApi {
  private readonly http = inject(HttpClient);

  getSites(): Observable<SiteProfile[]> {
    return this.http.get<SiteProfile[]>(`${BASE_URL}/sites`);
  }

  getSite(siteId: string): Observable<SiteProfile> {
    return this.http.get<SiteProfile>(`${BASE_URL}/sites/${siteId}`);
  }

  getTelemetry(siteId: string, from: Date, to: Date): Observable<Telemetry[]> {
    return this.http.get<Telemetry[]>(`${BASE_URL}/sites/${siteId}/telemetry`, {
      params: { from: from.toISOString(), to: to.toISOString() },
    });
  }
}
