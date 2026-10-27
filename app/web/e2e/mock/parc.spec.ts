import { expect, test } from '@playwright/test';

/** Parc de `MockEnergyApi` : 7 sites, SITE003 (Data Center Marseille) sans mesure récente, 7 alertes dans l'heure. */

test.beforeEach(async ({ page }) => {
  await page.goto('/parc');
});

test('affiche les indicateurs du parc', async ({ page }) => {
  const kpis = page.getByRole('region', { name: 'Indicateurs du parc' });

  await expect(kpis.getByText('Consommation instantanée')).toBeVisible();
  await expect(kpis.getByText('Charge moyenne du parc')).toBeVisible();
  await expect(kpis.getByText('Qualité des données')).toBeVisible();
});

test('signale le site sans mesure récente', async ({ page }) => {
  await expect(page.getByTestId('missing')).toContainText('Data Center Marseille');
});

test('liste les 7 sites et mène au détail d’un site', async ({ page }) => {
  const sites = page.getByRole('region', { name: /^Sites/ });

  await expect(sites.getByRole('heading')).toHaveText('Sites (7) — triés par charge');
  await expect(sites.locator('tbody tr')).toHaveCount(7);

  await sites.getByRole('link', { name: 'Usine Nantes Rezé' }).click();
  await expect(page).toHaveURL(/\/sites\/SITE007$/);
});

test('affiche les alertes de la dernière heure', async ({ page }) => {
  const alerts = page.getByRole('region', { name: /^Alertes actives/ });

  await expect(alerts.getByRole('heading')).toHaveText('Alertes actives (7)');
  await expect(alerts.getByTestId('alert')).toHaveCount(4);

  await alerts.getByRole('link', { name: 'Voir toutes les alertes →' }).click();
  await expect(page).toHaveURL(/\/alertes$/);
});
