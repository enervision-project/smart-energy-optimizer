/** Site suivi (table `sites`), tel que renvoyé par GET /api/v1/sites de core-api. */
export interface Site {
  siteId: string; // SITE001 … SITE007
  siteName: string;
  siteType: string; // office, factory, datacenter, retail, hospital
  location: string | null;
  capacityKw: number;
  status: string;
}
