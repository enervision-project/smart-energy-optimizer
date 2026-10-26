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
import { ParcSiteLoad, ParcSummary } from '../models/parc-summary';
import { PredictionPoint, PredictionSeries } from '../models/prediction';
import {
  DATA_QUALITIES,
  DataQuality,
  LatestReading,
  ReadingPoint,
  ReadingSeries,
  ReadingStep,
  ReadingSummary,
} from '../models/reading';
import { RecommendationResponse } from '../models/recommendation';
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
 * Site en perte réseau sur les 3 dernières heures : mesures reçues mais toutes à null, qualité `critical` ;
 * la consommation des 15 premières minutes de la panne est imputée (`previous_value`).
 */
const NETWORK_LOSS_SITE_ID = 'SITE003';
/**
 * Site avec des pannes de 2 minutes du capteur de consommation (`degraded`, imputées en `linear`), une panne du
 * capteur de température sur les 20 dernières minutes (`partial`) et une coupure de collecte d'une heure,
 * de 10 h à 9 h avant maintenant (aucune mesure reçue).
 */
const SENSOR_FAILURE_SITE_ID = 'SITE002';
const LOSS_MINUTES = 180;
const TEMPERATURE_FAILURE_MINUTES = 20;
const GAP_MINUTES_AGO: [number, number] = [600, 660];
/** Modèle enregistré dans MLflow (variable REGISTERED_MODEL_NAME de prediction-jobs). */
const PREDICTION_MODEL = 'enervision-hourly-consumption';
const PREDICTION_MODEL_VERSION = '3';
const STEP_MS: Record<ReadingStep, number> = {
  '1m': MINUTE_MS,
  '15m': 15 * MINUTE_MS,
  '1h': HOUR_MS,
};

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

  getReadingSeries(
    siteId: string,
    from: Date,
    to: Date,
    step: ReadingStep,
  ): Observable<ReadingSeries> {
    const found = SITES.find((s) => s.siteId === siteId);
    if (!found) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const now = Date.now();
    const width = STEP_MS[step];
    const start = floor(from.getTime(), width);
    const end = ceil(to.getTime(), width);
    const elapsedUntil = floor(now, MINUTE_MS);
    const points: ReadingPoint[] = [];
    for (let ts = start; ts < end; ts += width) {
      const until = Math.min(ts + width, elapsedUntil);
      points.push(
        aggregate(ts, minutes(found, ts, until, now), Math.max(0, (until - ts) / MINUTE_MS)),
      );
    }
    return of({
      siteId,
      step,
      from: new Date(start).toISOString(),
      to: new Date(end).toISOString(),
      points,
    });
  }

  getLatestReading(siteId: string): Observable<LatestReading | null> {
    const found = SITES.find((s) => s.siteId === siteId);
    if (!found) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const now = Date.now();
    const row = mockMinute(found, floor(now, MINUTE_MS) - MINUTE_MS, now);
    if (!row) {
      return of(null);
    }
    const { ts, imputationMethod, ...values } = row;
    return of({
      ...values,
      siteId,
      ts: new Date(ts).toISOString(),
      ageSeconds: Math.floor((now - ts) / 1000),
      imputationMethod,
    });
  }

  getReadingSummary(siteId: string, from: Date, to: Date): Observable<ReadingSummary> {
    const found = SITES.find((s) => s.siteId === siteId);
    if (!found) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const now = Date.now();
    const start = floor(from.getTime(), MINUTE_MS);
    const end = ceil(to.getTime(), MINUTE_MS);
    const elapsedEnd = Math.min(end, floor(now, MINUTE_MS));
    const rows = minutes(found, start, elapsedEnd, now);
    const hours = new Map<number, number[]>();
    let peak: MockMinute | null = null;
    for (const r of rows) {
      const hour = floor(r.ts, HOUR_MS);
      hours.set(hour, [
        ...(hours.get(hour) ?? []),
        ...(r.consumptionKw === null ? [] : [r.consumptionKw]),
      ]);
      if (r.consumptionKw !== null && (!peak || r.consumptionKw > peak.consumptionKw!)) {
        peak = r;
      }
    }
    const hourly = [...hours.values()].filter((kw) => kw.length).map((kw) => average(kw)!);
    const minutesExpected = Math.max(0, (elapsedEnd - start) / MINUTE_MS);
    const withConsumption = rows.filter((r) => r.consumptionKw !== null).length;
    return of({
      siteId,
      from: new Date(start).toISOString(),
      to: new Date(end).toISOString(),
      energyKwh: hourly.length
        ? round(
            hourly.reduce((a, b) => a + b, 0),
            2,
          )
        : null,
      hoursWithData: hourly.length,
      hoursExpected:
        elapsedEnd > start ? (ceil(elapsedEnd, HOUR_MS) - floor(start, HOUR_MS)) / HOUR_MS : 0,
      peakKw: peak?.consumptionKw ?? null,
      peakAt: peak ? new Date(peak.ts).toISOString() : null,
      availabilityPercent: minutesExpected
        ? round((100 * withConsumption) / minutesExpected)
        : null,
      minutesExpected,
      minutesReceived: rows.length,
      minutesWithConsumption: withConsumption,
      minutesImputed: rows.filter((r) => r.consumptionKwImputed !== null).length,
    });
  }

  /** Dernière minute collectée de chaque site, calculée comme core-api (valeur imputée si le capteur est en panne). */
  getParcSummary(): Observable<ParcSummary> {
    const now = Date.now();
    const sites: ParcSiteLoad[] = SITES.map((s) => {
      const row = mockMinute(s, floor(now, MINUTE_MS) - MINUTE_MS, now);
      const kw = row ? (row.consumptionKw ?? row.consumptionKwImputed) : null;
      return {
        siteId: s.siteId,
        siteName: s.siteName,
        currentConsumptionKw: kw,
        consumptionImputed: !!row && row.consumptionKw === null && kw !== null,
        capacityKw: s.capacityKw,
        loadPercent: kw === null ? null : round((100 * kw) / s.capacityKw),
        dataQuality: row?.dataQuality ?? null,
        ts: row ? new Date(row.ts).toISOString() : null,
        ageSeconds: row ? Math.floor((now - row.ts) / 1000) : null,
      };
    });
    const withData = sites.filter((s) => s.currentConsumptionKw !== null);
    const total = round(
      withData.reduce((sum, s) => sum + s.currentConsumptionKw!, 0),
      2,
    );
    const capacity = SITES.reduce((sum, s) => sum + s.capacityKw, 0);
    return of({
      timestamp: new Date(now).toISOString(),
      totalSites: sites.length,
      totalConsumptionKw: total,
      totalCapacityKw: capacity,
      averageLoadPercent: round((100 * total) / capacity),
      sitesWithoutData: sites.filter((s) => s.currentConsumptionKw === null).map((s) => s.siteId),
      sites,
    });
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

  /** Aucune donnée de mock pour les recommandations : l'application s'appuie uniquement sur l'API réelle. */
  /**
   * Prévisions comme les publie `prediction-jobs` : une série chaque heure pour les 24 heures suivantes.
   * Les heures passées gardent la prévision de leur série ; au-delà de l'heure en cours + 24 h, rien n'est publié.
   * Valeurs : profil du site avec un bruit différent des mesures, pour que prévu et mesuré se distinguent.
   */
  getPredictions(siteId: string, from: Date, to: Date): Observable<PredictionSeries> {
    const found = SITES.find((s) => s.siteId === siteId);
    if (!found) {
      return throwError(() => new Error(`Site inconnu : ${siteId}`));
    }
    const currentHour = floor(Date.now(), HOUR_MS);
    const covered = currentHour + 25 * HOUR_MS;
    const start = floor(from.getTime(), HOUR_MS);
    const end = ceil(to.getTime(), HOUR_MS);
    const points: PredictionPoint[] = [];
    for (let t = start; t < end; t += HOUR_MS) {
      const run = Math.min(t - HOUR_MS, currentHour) + 5 * MINUTE_MS;
      points.push(
        t < covered
          ? {
              ts: new Date(t).toISOString(),
              predictionKwh: round(consumption(found, new Date(t), t / MINUTE_MS + 7), 3),
              runId: `run-${new Date(run).toISOString()}`,
              modelName: PREDICTION_MODEL,
              modelVersion: PREDICTION_MODEL_VERSION,
              generatedAt: new Date(run).toISOString(),
            }
          : {
              ts: new Date(t).toISOString(),
              predictionKwh: null,
              runId: null,
              modelName: null,
              modelVersion: null,
              generatedAt: null,
            },
      );
    }
    return of({
      siteId,
      step: '1h',
      from: new Date(start).toISOString(),
      to: new Date(end).toISOString(),
      points,
    });
  }

  getRecommendations(): Observable<RecommendationResponse | null> {
    return of(null);
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

function site(
  siteId: string,
  siteType: string,
  siteName: string,
  location: string,
  capacityKw: number,
): Site {
  return { siteId, siteType, siteName, location, capacityKw, status: 'active' };
}

/** Ligne de `readings_raws` simulée. */
interface MockMinute {
  ts: number;
  source: string;
  consumptionKw: number | null;
  consumptionKwImputed: number | null;
  imputationMethod: string | null;
  voltageV: number | null;
  currentA: number | null;
  powerFactor: number | null;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  nullReasons: string[];
  dataQuality: DataQuality;
}

/** Minutes reçues de `[from, until)`, sans les minutes de la coupure de collecte. */
function minutes(s: Site, from: number, until: number, now: number): MockMinute[] {
  const rows: MockMinute[] = [];
  for (let t = from; t < until; t += MINUTE_MS) {
    const row = mockMinute(s, t, now);
    if (row) {
      rows.push(row);
    }
  }
  return rows;
}

/** Mesure de la minute `t`, ou `null` si elle n'a jamais été reçue. */
function mockMinute(s: Site, t: number, now: number): MockMinute | null {
  const minutesAgo = (floor(now, MINUTE_MS) - t) / MINUTE_MS;
  if (
    s.siteId === SENSOR_FAILURE_SITE_ID &&
    minutesAgo > GAP_MINUTES_AGO[0] &&
    minutesAgo <= GAP_MINUTES_AGO[1]
  ) {
    return null;
  }
  const index = t / MINUTE_MS;
  const kw = consumption(s, new Date(t), index);
  const voltage = round(400 + 3 * noise(index, 1));
  const powerFactor = round(0.93 + 0.02 * noise(index, 2), 3);
  const full: MockMinute = {
    ts: t,
    source: 'current',
    consumptionKw: kw,
    consumptionKwImputed: null,
    imputationMethod: null,
    voltageV: voltage,
    currentA: round((kw * 1000) / (Math.sqrt(3) * voltage * powerFactor)),
    powerFactor,
    temperatureCelsius: round(15 + 5 * Math.sin(((new Date(t).getHours() - 9) / 24) * 2 * Math.PI)),
    humidityPercent: round(60 + 8 * noise(index, 3)),
    nullReasons: [],
    dataQuality: 'good',
  };

  if (s.siteId === NETWORK_LOSS_SITE_ID && minutesAgo <= LOSS_MINUTES) {
    const lossStart = floor(now, MINUTE_MS) - LOSS_MINUTES * MINUTE_MS;
    const imputed = minutesAgo > LOSS_MINUTES - 15;
    return {
      ...full,
      consumptionKw: null,
      consumptionKwImputed: imputed
        ? consumption(s, new Date(lossStart - MINUTE_MS), lossStart / MINUTE_MS - 1)
        : null,
      imputationMethod: imputed ? 'previous_value' : null,
      voltageV: null,
      currentA: null,
      powerFactor: null,
      temperatureCelsius: null,
      humidityPercent: null,
      nullReasons: ['network_loss'],
      dataQuality: 'critical',
    };
  }
  if (s.siteId !== SENSOR_FAILURE_SITE_ID) {
    return full;
  }
  let row = full;
  if (minutesAgo <= TEMPERATURE_FAILURE_MINUTES) {
    row = {
      ...row,
      temperatureCelsius: null,
      nullReasons: ['temperature_sensor_failure'],
      dataQuality: 'partial',
    };
  }
  if (index % 47 < 2) {
    const before = consumption(s, new Date(t - (index % 47) * MINUTE_MS - MINUTE_MS), index - 1);
    const after = consumption(s, new Date(t + (2 - (index % 47)) * MINUTE_MS), index + 1);
    row = {
      ...row,
      consumptionKw: null,
      consumptionKwImputed: round(before + ((after - before) * ((index % 47) + 1)) / 3, 2),
      imputationMethod: 'linear',
      nullReasons: ['consumption_sensor_failure', ...row.nullReasons],
      dataQuality: 'degraded',
    };
  }
  return row;
}

/** Point de courbe calculé comme core-api : moyennes, pire qualité, raisons des NULL et compteurs. */
function aggregate(ts: number, rows: MockMinute[], minutesExpected: number): ReadingPoint {
  const worst = Math.max(-1, ...rows.map((r) => DATA_QUALITIES.indexOf(r.dataQuality)));
  return {
    ts: new Date(ts).toISOString(),
    consumptionKw: average(rows.map((r) => r.consumptionKw)),
    consumptionKwImputed: average(rows.map((r) => r.consumptionKw ?? r.consumptionKwImputed)),
    voltageV: average(rows.map((r) => r.voltageV)),
    currentA: average(rows.map((r) => r.currentA)),
    powerFactor: average(
      rows.map((r) => r.powerFactor),
      3,
    ),
    temperatureCelsius: average(rows.map((r) => r.temperatureCelsius)),
    humidityPercent: average(rows.map((r) => r.humidityPercent)),
    dataQuality: worst < 0 ? null : DATA_QUALITIES[worst],
    nullReasons: [...new Set(rows.flatMap((r) => r.nullReasons))].sort((a, b) =>
      a.localeCompare(b),
    ),
    minutesExpected,
    minutesReceived: rows.length,
    minutesBackfilled: 0,
    minutesImputed: rows.filter((r) => r.consumptionKwImputed !== null).length,
    imputationMethods: [
      ...new Set(rows.flatMap((r) => (r.imputationMethod ? [r.imputationMethod] : []))),
    ].sort((a, b) => a.localeCompare(b)),
  };
}

function average(values: (number | null)[], digits = 2): number | null {
  const present = values.filter((v): v is number => v !== null);
  return present.length ? round(present.reduce((a, b) => a + b, 0) / present.length, digits) : null;
}

function floor(t: number, width: number): number {
  return Math.floor(t / width) * width;
}

function ceil(t: number, width: number): number {
  return Math.ceil(t / width) * width;
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
