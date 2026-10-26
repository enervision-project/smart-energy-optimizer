import { DataQuality } from './reading';

/** Consommation actuelle d'un site dans GET /api/v1/stats/summary de core-api. */
export interface ParcSiteLoad {
  siteId: string;
  siteName: string;
  /** Valeur brute de la dernière mesure, ou sa valeur imputée si le capteur est en panne ; `null` sans mesure récente. */
  currentConsumptionKw: number | null;
  /** Vrai quand `currentConsumptionKw` est une estimation. */
  consumptionImputed: boolean;
  capacityKw: number;
  loadPercent: number | null;
  /** Qualité de la dernière mesure, `null` sans mesure récente (moins de 3 min). */
  dataQuality: DataQuality | null;
  ts: string | null;
  ageSeconds: number | null;
}

/**
 * Consommation actuelle des sites visibles (même forme que `/stats/summary` de l'API Mock, en camelCase).
 * Les sites de `sitesWithoutData` sont exclus de `totalConsumptionKw` : la vue doit le signaler.
 */
export interface ParcSummary {
  timestamp: string;
  totalSites: number;
  totalConsumptionKw: number;
  /** Capacité de tous les sites visibles. */
  totalCapacityKw: number;
  averageLoadPercent: number | null;
  sitesWithoutData: string[];
  sites: ParcSiteLoad[];
}
