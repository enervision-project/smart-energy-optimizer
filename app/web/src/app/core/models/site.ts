/** Site suivi (table `sites`, même forme que GET /api/v1/sites de l'API Mock). */
export interface Site {
  site_id: string; // SITE001 … SITE007
  site_name: string;
  site_type: string; // office, factory, datacenter, retail, hospital
  location: string | null;
  capacity_kw: number;
  status: string;
}
