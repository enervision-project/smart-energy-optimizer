export const RECOMMENDATION_QUALITIES = ['good', 'medium', 'bad', 'unknown'] as const;
export type RecommendationQuality = (typeof RECOMMENDATION_QUALITIES)[number];

export const RECOMMENDATION_TYPES = ['POWER_FACTOR', 'VOLTAGE', 'LOAD_RATE'] as const;
export type RecommendationType = (typeof RECOMMENDATION_TYPES)[number];

export interface RecommendationItem {
  type: RecommendationType | string;
  label: string;
  value: number | null;
  unit: string;
  quality: RecommendationQuality | string;
  shortRecommendation: string;
  longRecommendation: string;
}

export interface RecommendationResponse {
  siteId: string;
  timestamp: string;
  items: RecommendationItem[];
}
