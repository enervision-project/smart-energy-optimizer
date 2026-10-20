import { Observable } from 'rxjs';
import { Reading } from '../models/reading';
import { Site } from '../models/site';

/** Seul point d'accès aux données pour les pages : l'implémentation (mock ou HTTP) est choisie dans `app.config.ts`. */
export abstract class EnergyApi {
  abstract getSites(): Observable<Site[]>;
  abstract getSite(siteId: string): Observable<Site>;
  /** Mesures horaires de `from` (inclus) à `to` (exclu). */
  abstract getReadings(siteId: string, from: Date, to: Date): Observable<Reading[]>;
}
