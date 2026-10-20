import { Service } from '@angular/core';
import { Observable, of, throwError } from 'rxjs';
import {
  ALERT_SEVERITIES,
  Alert,
  AlertFilters,
  AlertSeverity,
  AlertSummary,
  AlertType,
  Page,
} from '../models/alert';
import { ParcSiteSummary, ParcSummary } from '../models/parc-summary';
import { DataQuality, Reading } from '../models/reading';
import { Site } from '../models/site';
import { EnergyApi } from './energy-api';

const HOUR_MS = 3_600_000;
const MINUTE_MS = 60_000;

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
 * Profils de charge par type, en fraction de `capacityKw`, inspirés des profils du jeu de données
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

/**
 * Incidents simulés, en heures avant l'heure courante (1 = l'heure qui vient de s'écouler),
 * pour que la vue site (48 h) et la vue parc (24 h) affichent les mêmes valeurs.
 * - SITE003 : perte réseau sur les 3 dernières heures, toutes les mesures à null (`critical`) ;
 * - SITE002 : panne des capteurs de consommation (`degraded`) puis de température (`partial`).
 */
const NETWORK_LOSS_SITE_ID = 'SITE003';
const NETWORK_LOSS_HOURS = 3;
const SENSOR_FAILURE_SITE_ID = 'SITE002';
const DEGRADED_HOURS_AGO = [40, 39, 38];
const PARTIAL_HOURS_AGO = [18, 17, 16, 15];

/** Seuils fixes par site observés sur GET /api/v1/alerts de l'API Mock. */
const ALERT_THRESHOLDS: Record<string, number> = {
  SITE001: 135,
  SITE002: 720,
  SITE003: 630,
  SITE004: 270,
  SITE005: 405,
  SITE006: 117,
  SITE007: 675,
};

/** Début des messages de l'API Mock, suivi du nom du site. */
const ALERT_MESSAGES: Record<AlertType, string> = {
  spike: 'Pic de consommation détecté sur',
  threshold: 'Seuil de consommation dépassé sur',
  anomaly: 'Comportement anormal détecté sur',
  outage: 'Risque de surcharge sur',
  sensor: 'Défaillance capteur détectée sur',
};

/** Alertes du mock : [site, il y a N minutes, sévérité, type, dépassement du seuil]. Les deux dernières ont plus d'une heure. */
const ALERTS: [string, number, AlertSeverity, AlertType, number][] = [
  ['SITE003', 4, 'critical', 'outage', 1.31],
  ['SITE002', 12, 'high', 'spike', 1.27],
  ['SITE001', 19, 'medium', 'threshold', 1.22],
  ['SITE005', 26, 'medium', 'anomaly', 1.36],
  ['SITE007', 33, 'critical', 'outage', 1.34],
  ['SITE006', 41, 'low', 'sensor', 1.26],
  ['SITE002', 52, 'medium', 'threshold', 1.14],
  ['SITE004', 95, 'high', 'spike', 1.25],
  ['SITE001', 180, 'low', 'anomaly', 1.18],
];

/** Données factices pour développer sans back-end (voir `environment.development.ts`). */
@Service()
export class MockEnergyApi extends EnergyApi {
  getSites(): Observable<Site[]> {
    return of(SITES);
  }

  getSite(siteId: string): Observable<Site> {
    const found = SITES.find((s) => s.siteId === siteId);
    return found ? of(found) : throwError(() => new Error(`Site inconnu : ${siteId}`));
  }

  getReadings(siteId: string, from: Date, to: Date): Observable<Reading[]> {
    const found = SITES.find((s) => s.siteId === siteId);
    return found
      ? of(series(found, from, to))
      : throwError(() => new Error(`Site inconnu : ${siteId}`));
  }

  getAlerts(filters: AlertFilters, page: number, size: number): Observable<Page<Alert>> {
    if (filters.siteId && !SITES.some((s) => s.siteId === filters.siteId)) {
      return throwError(() => new Error(`Site inconnu : ${filters.siteId}`));
    }
    const to = filters.to ?? new Date();
    const from = filters.from ?? new Date(to.getTime() - HOUR_MS);
    const matching = mockAlerts().filter(
      (a) =>
        (!filters.siteId || a.siteId === filters.siteId) &&
        (!filters.severity?.length || filters.severity.includes(a.severity as AlertSeverity)) &&
        (!filters.type?.length || filters.type.includes(a.type as AlertType)) &&
        new Date(a.timestamp) >= from &&
        new Date(a.timestamp) <= to,
    );
    return of({
      content: matching.slice(page * size, (page + 1) * size),
      page: {
        size,
        number: page,
        totalElements: matching.length,
        totalPages: Math.ceil(matching.length / size),
      },
    });
  }

  getAlertSummary(siteId?: string): Observable<AlertSummary> {
    const since = new Date(Date.now() - HOUR_MS);
    const recent = mockAlerts().filter((a) => a.recent && (!siteId || a.siteId === siteId));
    const bySeverity = Object.fromEntries(
      ALERT_SEVERITIES.map((sev) => [sev, recent.filter((a) => a.severity === sev).length]),
    ) as Record<AlertSeverity, number>;
    return of({ since: since.toISOString(), total: recent.length, bySeverity });
  }

  getParcReadings(from: Date, to: Date): Observable<Reading[]> {
    return of(SITES.flatMap((s) => series(s, from, to)));
  }

  /** Calculée comme l'API Mock : dernière mesure de chaque site, sites sans mesure exclus des totaux. */
  getParcSummary(): Observable<ParcSummary> {
    const to = new Date(currentHour());
    const from = new Date(to.getTime() - HOUR_MS);
    const sites: ParcSiteSummary[] = SITES.map((s) => {
      const last = series(s, from, to)[0];
      const kw = last.consumption_kw;
      return {
        site_id: s.siteId,
        site_name: s.siteName,
        current_consumption_kw: kw,
        capacity_kw: s.capacityKw,
        load_percent: kw === null ? null : round((kw / s.capacityKw) * 100),
        data_quality: last.data_quality,
      };
    });
    const reporting = sites.filter((s) => s.current_consumption_kw !== null);
    const total = reporting.reduce((sum, s) => sum + (s.current_consumption_kw ?? 0), 0);
    const capacity = SITES.reduce((sum, s) => sum + s.capacityKw, 0);
    return of({
      timestamp: to.toISOString(),
      total_sites: SITES.length,
      total_consumption_kw: round(total),
      total_capacity_kw: capacity,
      average_load_percent: round((total / capacity) * 100),
      sites,
    });
  }
}

/** Alertes datées par rapport à maintenant, de la plus récente à la plus ancienne. */
function mockAlerts(): Alert[] {
  const now = Date.now();
  return ALERTS.map(([siteId, minutesAgo, severity, type, ratio]) => {
    const s = SITES.find((x) => x.siteId === siteId)!;
    const timestamp = new Date(now - minutesAgo * MINUTE_MS);
    const threshold = ALERT_THRESHOLDS[siteId];
    return {
      alertId: `ALR-${siteId}-${Math.floor(timestamp.getTime() / 1000)}`,
      siteId,
      siteName: s.siteName,
      timestamp: timestamp.toISOString(),
      severity,
      type,
      message: `${ALERT_MESSAGES[type]} ${s.siteName}`,
      value: round(threshold * ratio, 2),
      threshold,
      recent: minutesAgo < 60,
    };
  });
}

function currentHour(): number {
  return Math.floor(Date.now() / HOUR_MS) * HOUR_MS;
}

function series(s: Site, from: Date, to: Date): Reading[] {
  const now = currentHour();
  const readings: Reading[] = [];
  for (let t = from.getTime(); t < to.getTime(); t += HOUR_MS) {
    readings.push(reading(s, new Date(t), (now - t) / HOUR_MS));
  }
  return readings;
}

function site(
  siteId: string,
  siteType: string,
  siteName: string,
  location: string,
  capacityKw: number,
): Site {
  return { siteId, siteType, siteName, location, capacityKw, status: 'active' };
}

function reading(s: Site, date: Date, hoursAgo: number): Reading {
  const index = date.getTime() / HOUR_MS;
  const kw = consumption(s, date, index);
  const voltage = round(400 + 3 * noise(index, 1));
  const powerFactor = round(0.93 + 0.02 * noise(index, 2), 3);
  const full: Reading = {
    site_id: s.siteId,
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

  if (s.siteId === NETWORK_LOSS_SITE_ID && hoursAgo >= 1 && hoursAgo <= NETWORK_LOSS_HOURS) {
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
  if (s.siteId === SENSOR_FAILURE_SITE_ID && DEGRADED_HOURS_AGO.includes(hoursAgo)) {
    return withNulls(full, 'degraded', [
      'consumption_kw',
      'consumption_kwh',
      'voltage_v',
      'current_a',
      'power_factor',
    ]);
  }
  if (s.siteId === SENSOR_FAILURE_SITE_ID && PARTIAL_HOURS_AGO.includes(hoursAgo)) {
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
  const p = PROFILES[s.siteType] ?? PROFILES['office'];
  const hour = date.getHours();
  const day = date.getDay();
  const working =
    hour >= p.hours[0] && hour < p.hours[1] && (!p.weekdaysOnly || (day >= 1 && day <= 5));
  let ratio = working ? p.peak : p.base;
  if (s.siteType === 'factory' && working && hour >= 10 && hour <= 12) {
    ratio = 0.92;
  }
  return round(s.capacityKw * (ratio + 0.03 * noise(index, s.capacityKw)));
}

function noise(index: number, seed: number): number {
  return (Math.sin(index * 12.9898 + seed * 78.233) * 43758.5453) % 1;
}

function round(value: number, digits = 1): number {
  const f = 10 ** digits;
  return Math.round(value * f) / f;
}
