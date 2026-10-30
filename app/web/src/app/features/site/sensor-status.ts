import { LatestReading, STALE_AFTER_SECONDS } from '../../core/models/reading';

export type SensorState = 'ok' | 'failing' | 'unknown';

export interface SensorStatus {
  key: string;
  label: string;
  state: SensorState;
}

const SENSORS: { key: string; label: string; reason: string }[] = [
  { key: 'consumption', label: 'Consommation', reason: 'consumption_sensor_failure' },
  { key: 'electrical', label: 'Électrique', reason: 'electrical_sensor_failure' },
  { key: 'temperature', label: 'Température', reason: 'temperature_sensor_failure' },
  { key: 'humidity', label: 'Humidité', reason: 'humidity_sensor_failure' },
  { key: 'network', label: 'Réseau', reason: 'network_loss' },
];

const NULL_REASON_LABELS: Record<string, string> = {
  consumption_sensor_failure: 'capteur de consommation en panne',
  electrical_sensor_failure: 'capteurs électriques en panne',
  temperature_sensor_failure: 'capteur de température en panne',
  humidity_sensor_failure: 'capteur d’humidité en panne',
  network_loss: 'perte réseau',
};

const IMPUTATION_LABELS: Record<string, string> = {
  previous_value: 'valeur précédente',
  linear: 'interpolation linéaire',
};

/** Without a recent reading sensors are "unknown", not "OK"; on network loss only that failure is certain. */
export function sensorStatuses(latest: LatestReading | null): SensorStatus[] {
  const stale = !latest || latest.ageSeconds > STALE_AFTER_SECONDS;
  const networkLoss = latest?.nullReasons.includes('network_loss') ?? false;
  return SENSORS.map(({ key, label, reason }) => {
    let state: SensorState;
    if (stale) {
      state = 'unknown';
    } else if (latest.nullReasons.includes(reason)) {
      state = 'failing';
    } else {
      state = networkLoss ? 'unknown' : 'ok';
    }
    return { key, label, state };
  });
}

export function nullReasonLabel(reason: string): string {
  return NULL_REASON_LABELS[reason] ?? reason;
}

export function imputationLabel(method: string): string {
  return IMPUTATION_LABELS[method] ?? method;
}
