export interface Alert {
  alert_id: string;
  site_id: string;
  alert_type: string;              // spike, threshold, anomaly, outage, sensor
  severity: 'low' | 'medium' | 'high' | 'critical';
  viewed_at: string | null;        // null = non vue
}
