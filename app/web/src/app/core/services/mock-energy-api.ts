import { Service } from '@angular/core';
import { Observable, of, throwError } from 'rxjs';
import { SiteProfile } from '../models/site-profile';
import { Telemetry } from '../models/telemetry';
import { EnergyApi } from './energy-api';

const HOUR_MS = 3_600_000;

const SITES: SiteProfile[] = [
  site(1, 'Bureaux Paris La Défense', 'office', 120, 260, { weekdays: '08:00-19:00' }),
  site(2, 'Bureaux Lyon Part-Dieu', 'office', 90, 200, { weekdays: '08:00-19:00' }),
  site(3, 'Usine Lyon Vénissieux', 'factory', 420, 760, { weekdays: '06:00-22:00' }),
  site(4, 'Usine Lille Roubaix', 'factory', 380, 650, { weekdays: '06:00-22:00' }),
  site(5, 'Data center Marseille', 'data_center', 900, 1100, { all: '00:00-24:00' }),
  site(6, 'Centre commercial Nantes Atlantis', 'mall', 300, 620, { all: '09:00-21:00' }),
  site(7, 'Hôpital Toulouse Purpan', 'hospital', 400, 700, { all: '00:00-24:00' }),
];

/** Site en perte réseau sur une partie de la fenêtre : trous (null) puis points imputés. */
const DEGRADED_SITE_ID = SITES[2].site_id;

/** Données factices pour développer sans back-end (voir `environment.development.ts`). */
@Service()
export class MockEnergyApi extends EnergyApi {
  getSites(): Observable<SiteProfile[]> {
    return of(SITES);
  }

  getSite(siteId: string): Observable<SiteProfile> {
    const found = SITES.find((s) => s.site_id === siteId);
    return found ? of(found) : throwError(() => new Error(`Site inconnu : ${siteId}`));
  }

  getTelemetry(siteId: string, from: Date, to: Date): Observable<Telemetry[]> {
    const profile = SITES.find((s) => s.site_id === siteId);
    if (!profile) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const readings: Telemetry[] = [];
    for (let t = from.getTime(), i = 0; t < to.getTime(); t += HOUR_MS, i++) {
      readings.push(reading(profile, new Date(t), i));
    }
    return of(readings);
  }
}

function site(
  n: number,
  name: string,
  site_type: string,
  base_consumption: number,
  peak_consumption: number,
  operating_hours: Record<string, string>,
): SiteProfile {
  const site_id = `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
  return { site_id, name, site_type, base_consumption, peak_consumption, operating_hours };
}

function reading(profile: SiteProfile, date: Date, index: number): Telemetry {
  const base = { measured_at: date.toISOString(), site_id: profile.site_id };
  if (profile.site_id === DEGRADED_SITE_ID) {
    if (index >= 8 && index < 11) {
      return { ...base, consumption_kwh: null, quality_status: 'missing', correction_reason: null };
    }
    if (index >= 30 && index < 34) {
      return {
        ...base,
        consumption_kwh: consumption(profile, date, index),
        quality_status: 'imputed',
        correction_reason: 'linear_interpolation',
      };
    }
  }
  return {
    ...base,
    consumption_kwh: consumption(profile, date, index),
    quality_status: 'valid',
    correction_reason: null,
  };
}

/** Courbe déterministe : talon + activité selon le type de site + bruit, avec un dépassement du seuil pour les usines. */
function consumption(profile: SiteProfile, date: Date, index: number): number {
  const hour = date.getHours();
  const range = profile.peak_consumption - profile.base_consumption;
  const noise = (Math.sin(index * 12.9898 + profile.base_consumption) * 43758.5453) % 1;
  let value = profile.base_consumption + range * activity(profile.site_type, hour) * 0.9;
  if (profile.site_type === 'factory' && hour >= 10 && hour <= 12) {
    value = profile.peak_consumption * 1.12;
  }
  return Math.round((value + noise * 0.04 * profile.peak_consumption) * 10) / 10;
}

function activity(siteType: string, hour: number): number {
  switch (siteType) {
    case 'office':
      return hour >= 8 && hour < 19 ? 1 : 0.1;
    case 'factory':
      return hour >= 6 && hour < 22 ? 0.85 : 0.1;
    case 'mall':
      return hour >= 9 && hour < 21 ? 1 : 0.15;
    case 'hospital':
      return hour >= 8 && hour < 20 ? 0.8 : 0.4;
    default:
      return 0.5;
  }
}
