import { Service } from '@angular/core';
import { Observable, of, throwError } from 'rxjs';
import { DataQuality, Reading } from '../models/reading';
import { Site } from '../models/site';
import { EnergyApi } from './energy-api';

const HOUR_MS = 3_600_000;

/** Réponse réelle de GET /api/v1/sites de l'API Mock de l'école. */
const SITES: Site[] = [
  site('SITE001', 'office', 'Bureau Paris La Défense', 'Paris, France', 200),
  site('SITE002', 'factory', 'Usine Lyon Vénissieux', 'Lyon, France', 1000),
  site('SITE003', 'datacenter', 'Data Center Marseille', 'Marseille, France', 800),
  site('SITE004', 'retail', 'Centre Commercial Lille', 'Lille, France', 400),
  site('SITE005', 'hospital', 'Hôpital Toulouse Purpan', 'Toulouse, France', 600),
  site('SITE006', 'office', 'Bureau Bordeaux Centre', 'Bordeaux, France', 180),
  site('SITE007', 'factory', 'Usine Nantes Rezé', 'Nantes, France', 950),
];

/**
 * Profils de charge par type, en fraction de `capacity_kw`, inspirés des profils du jeu de données
 * fourni (talon, pic, heures et jours d'activité).
 */
const PROFILES: Record<
  string,
  { base: number; peak: number; hours: [number, number]; weekdaysOnly: boolean }
> = {
  office: { base: 0.25, peak: 0.75, hours: [8, 19], weekdaysOnly: true },
  factory: { base: 0.2, peak: 0.8, hours: [6, 22], weekdaysOnly: true },
  datacenter: { base: 0.7, peak: 0.85, hours: [0, 24], weekdaysOnly: false },
  retail: { base: 0.25, peak: 0.75, hours: [9, 21], weekdaysOnly: false },
  hospital: { base: 0.55, peak: 0.75, hours: [8, 20], weekdaysOnly: false },
};

/** Site en perte réseau sur les 3 dernières heures : toutes les mesures à null, qualité `critical`. */
const NETWORK_LOSS_SITE_ID = 'SITE003';
/** Site avec une panne des capteurs de consommation (`degraded`) puis de température (`partial`). */
const SENSOR_FAILURE_SITE_ID = 'SITE002';

/** Données factices pour développer sans back-end (voir `environment.development.ts`). */
@Service()
export class MockEnergyApi extends EnergyApi {
  getSites(): Observable<Site[]> {
    return of(SITES);
  }

  getSite(siteId: string): Observable<Site> {
    const found = SITES.find((s) => s.site_id === siteId);
    return found ? of(found) : throwError(() => new Error(`Site inconnu : ${siteId}`));
  }

  getReadings(siteId: string, from: Date, to: Date): Observable<Reading[]> {
    const found = SITES.find((s) => s.site_id === siteId);
    if (!found) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const lossStart = Math.floor(Date.now() / HOUR_MS) * HOUR_MS - 3 * HOUR_MS;
    const readings: Reading[] = [];
    for (let t = from.getTime(), i = 0; t < to.getTime(); t += HOUR_MS, i++) {
      readings.push(reading(found, new Date(t), i, t >= lossStart));
    }
    return of(readings);
  }
}

function site(
  site_id: string,
  site_type: string,
  site_name: string,
  location: string,
  capacity_kw: number,
): Site {
  return { site_id, site_type, site_name, location, capacity_kw, status: 'active' };
}

function reading(s: Site, date: Date, index: number, inLossWindow: boolean): Reading {
  const kw = consumption(s, date, index);
  const voltage = round(400 + 3 * noise(index, 1));
  const powerFactor = round(0.93 + 0.02 * noise(index, 2), 3);
  const full: Reading = {
    site_id: s.site_id,
    ts: date.toISOString(),
    consumption_kw: kw,
    consumption_kwh: kw,
    voltage_v: voltage,
    current_a: round((kw * 1000) / (Math.sqrt(3) * voltage * powerFactor)),
    power_factor: powerFactor,
    temperature_celsius: round(15 + 5 * Math.sin(((date.getHours() - 9) / 24) * 2 * Math.PI)),
    humidity_percent: round(60 + 8 * noise(index, 3)),
    data_quality: 'good',
  };

  if (s.site_id === NETWORK_LOSS_SITE_ID && inLossWindow) {
    return withNulls(full, 'critical', [
      'consumption_kw',
      'consumption_kwh',
      'voltage_v',
      'current_a',
      'power_factor',
      'temperature_celsius',
      'humidity_percent',
    ]);
  }
  if (s.site_id === SENSOR_FAILURE_SITE_ID && index >= 8 && index < 11) {
    return withNulls(full, 'degraded', [
      'consumption_kw',
      'consumption_kwh',
      'voltage_v',
      'current_a',
      'power_factor',
    ]);
  }
  if (s.site_id === SENSOR_FAILURE_SITE_ID && index >= 30 && index < 34) {
    return withNulls(full, 'partial', ['temperature_celsius']);
  }
  return full;
}

function withNulls(r: Reading, quality: DataQuality, fields: (keyof Reading)[]): Reading {
  const copy: Record<string, unknown> = { ...r, data_quality: quality };
  for (const f of fields) {
    copy[f] = null;
  }
  return copy as unknown as Reading;
}

/** Courbe déterministe : talon + activité selon le profil du type de site + bruit, avec une pointe en fin de matinée pour les usines. */
function consumption(s: Site, date: Date, index: number): number {
  const p = PROFILES[s.site_type] ?? PROFILES['office'];
  const hour = date.getHours();
  const day = date.getDay();
  const working =
    hour >= p.hours[0] && hour < p.hours[1] && (!p.weekdaysOnly || (day >= 1 && day <= 5));
  let ratio = working ? p.peak : p.base;
  if (s.site_type === 'factory' && working && hour >= 10 && hour <= 12) {
    ratio = 0.92;
  }
  return round(s.capacity_kw * (ratio + 0.03 * noise(index, s.capacity_kw)));
}

function noise(index: number, seed: number): number {
  return (Math.sin(index * 12.9898 + seed * 78.233) * 43758.5453) % 1;
}

function round(value: number, digits = 1): number {
  const f = 10 ** digits;
  return Math.round(value * f) / f;
}
