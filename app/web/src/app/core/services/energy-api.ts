import { Observable } from 'rxjs';
import { SiteProfile } from '../models/site-profile';
import { Telemetry } from '../models/telemetry';

/** Seul point d'accès aux données pour les pages : l'implémentation (mock ou HTTP) est choisie dans `app.config.ts`. */
export abstract class EnergyApi {
  abstract getSites(): Observable<SiteProfile[]>;
  abstract getSite(siteId: string): Observable<SiteProfile>;
  /** Mesures horaires de `from` (inclus) à `to` (exclu). */
  abstract getTelemetry(siteId: string, from: Date, to: Date): Observable<Telemetry[]>;
}
