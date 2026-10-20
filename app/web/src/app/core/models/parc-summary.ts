import { DataQuality } from './reading';

/** Situation d'un site dans la synthèse du parc. `null` quand le site n'a pas de mesure récente. */
export interface ParcSiteSummary {
  site_id: string;
  site_name: string;
  current_consumption_kw: number | null;
  capacity_kw: number;
  load_percent: number | null;
  data_quality: DataQuality;
}

/**
 * Synthèse instantanée du parc (même forme que GET /api/v1/stats/summary de l'API Mock).
 * Les sites sans mesure sont exclus de `total_consumption_kw` : la vue doit le signaler.
 */
export interface ParcSummary {
  timestamp: string;
  total_sites: number;
  total_consumption_kw: number;
  total_capacity_kw: number;
  average_load_percent: number;
  sites: ParcSiteSummary[];
}
