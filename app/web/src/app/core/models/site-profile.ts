export interface SiteProfile {
  site_id: string;                 // uuid
  name: string;
  site_type: string;               // bureau, usine, data_center…
  base_consumption: number;
  peak_consumption: number;
  operating_hours: Record<string, unknown>;   // jsonb, format à préciser
}
