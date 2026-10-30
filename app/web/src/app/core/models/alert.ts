/** The ETL loads alerts every minute: reading them more often is pointless. */
export const ALERT_REFRESH_MS = 30_000;

export const ALERT_SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

export const ALERT_TYPES = ['spike', 'threshold', 'anomaly', 'outage', 'sensor'] as const;
export type AlertType = (typeof ALERT_TYPES)[number];

/** Mock API alerts are random on each call: no status or acknowledgement, only `recent`. */
export interface Alert {
  alertId: string;
  siteId: string;
  siteName: string;
  timestamp: string; // ISO 8601 UTC
  /** Raw database value: may fall outside `AlertSeverity` and must stay displayable. */
  severity: string;
  type: string;
  message: string;
  value: number | null;
  threshold: number;
  recent: boolean;
}

export interface AlertFilters {
  siteId?: string;
  severity?: AlertSeverity[];
  type?: AlertType[];
  /** Defaults to one hour before `to` on the API side. */
  from?: Date;
  to?: Date;
}

/** Page Spring Data (`PagedModel`). */
export interface Page<T> {
  content: T[];
  page: { size: number; number: number; totalElements: number; totalPages: number };
}

export interface AlertSummary {
  since: string;
  total: number;
  bySeverity: Record<AlertSeverity, number>;
}
