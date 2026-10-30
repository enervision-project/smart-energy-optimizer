/** An unknown value is displayed as is. */
const SEVERITY_LABELS: Record<string, string> = {
  low: 'Faible',
  medium: 'Moyenne',
  high: 'Élevée',
  critical: 'Critique',
};

const TYPE_LABELS: Record<string, string> = {
  spike: 'Pic',
  threshold: 'Seuil dépassé',
  anomaly: 'Anomalie',
  outage: 'Risque de coupure',
  sensor: 'Capteur',
};

export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity] ?? severity;
}

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}
