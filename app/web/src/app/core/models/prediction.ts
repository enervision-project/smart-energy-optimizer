export interface Prediction {
  prediction_id: string;
  site_id: string;
  target_date: string;             // date (YYYY-MM-DD)
  predicted_kwh: number;
  model_version: string;
}
