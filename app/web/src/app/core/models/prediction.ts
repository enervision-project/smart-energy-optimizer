/** An hour without a published forecast is returned with `null` values. */
export interface PredictionPoint {
  ts: string;
  /** Energy over the hour, in kWh: also the hour's average power, in kW. */
  predictionKwh: number | null;
  runId: string | null;
  modelName: string | null;
  modelVersion: string | null;
  generatedAt: string | null;
}

export interface PredictionSeries {
  siteId: string;
  step: '1h';
  from: string;
  to: string;
  points: PredictionPoint[];
}
