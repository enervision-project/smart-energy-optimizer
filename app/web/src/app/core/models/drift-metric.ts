export interface DriftMetric {
  drift_id: string;                // uuid
  site_id: string;
  mae_7d: number;                  // MAE sur 7 jours glissants
  retrain_triggered: boolean;
  computed_at?: string;            // timestamptz ISO 8601 — proposé à l'équipe, non validé
  model_version?: string;          // lien avec predictions.model_version — proposé, non validé
}
