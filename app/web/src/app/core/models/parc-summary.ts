import { DataQuality } from './reading';

export interface ParcSiteLoad {
  siteId: string;
  siteName: string;
  /** Raw value of the last reading, or its imputed value when the sensor failed; `null` without a recent reading. */
  currentConsumptionKw: number | null;
  consumptionImputed: boolean;
  capacityKw: number;
  loadPercent: number | null;
  dataQuality: DataQuality | null;
  ts: string | null;
  ageSeconds: number | null;
}

/** Sites in `sitesWithoutData` are excluded from `totalConsumptionKw`: the view must say so. */
export interface ParcSummary {
  timestamp: string;
  totalSites: number;
  totalConsumptionKw: number;
  totalCapacityKw: number;
  averageLoadPercent: number | null;
  sitesWithoutData: string[];
  sites: ParcSiteLoad[];
}
