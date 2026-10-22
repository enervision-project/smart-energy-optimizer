/** L'ETL charge les alertes chaque minute : les relire plus souvent n'apporterait rien. */
export const ALERT_REFRESH_MS = 30_000;

/** Sévérités de l'API Mock, de la moins à la plus grave. */
export const ALERT_SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

/** spike : pic soudain, threshold : seuil dépassé, anomaly : comportement anormal, outage : risque de coupure, sensor : capteur en panne. */
export const ALERT_TYPES = ['spike', 'threshold', 'anomaly', 'outage', 'sensor'] as const;
export type AlertType = (typeof ALERT_TYPES)[number];

/**
 * Alerte renvoyée par GET /api/v1/alerts de core-api.
 * Les alertes de l'API Mock sont tirées au hasard à chaque appel : pas de statut ni d'acquittement,
 * seulement `recent` (moins d'une heure). Voir services/core-api/docs/alertes.md.
 */
export interface Alert {
  alertId: string;
  siteId: string;
  siteName: string;
  timestamp: string; // ISO 8601 UTC
  /** Valeur brute en base : une valeur hors `AlertSeverity` est possible et doit rester affichable. */
  severity: string;
  type: string;
  message: string;
  value: number | null;
  threshold: number;
  recent: boolean;
}

/** Filtres de GET /api/v1/alerts ; un champ absent ou vide = pas de filtre. */
export interface AlertFilters {
  siteId?: string;
  severity?: AlertSeverity[];
  type?: AlertType[];
  /** Début de période ; une heure avant `to` par défaut côté API. */
  from?: Date;
  to?: Date;
}

/** Page Spring Data (`PagedModel`). */
export interface Page<T> {
  content: T[];
  page: { size: number; number: number; totalElements: number; totalPages: number };
}

/** GET /api/v1/alerts/summary : alertes de la dernière heure. */
export interface AlertSummary {
  since: string;
  /** Inclut les alertes de sévérité inconnue. */
  total: number;
  bySeverity: Record<AlertSeverity, number>;
}
