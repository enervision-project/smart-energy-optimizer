import { expect, test } from '@playwright/test';

/**
 * Sites de `MockEnergyApi` : SITE003 en perte réseau sur les 3 dernières heures, SITE002 avec une
 * panne du capteur de température sur les 20 dernières minutes et 2 alertes dans l'heure.
 */

test('affiche le profil, la dernière mesure et la synthèse d’un site', async ({ page }) => {
  await page.goto('/sites/SITE001');

  await expect(page.getByText('Paris, France · capacité 200 kW')).toBeVisible();
  await expect(page.getByTestId('measure-consumptionKw')).toBeVisible();
  await expect(page.getByTestId('freshness')).toBeVisible();
  await expect(page.getByTestId('quality-band')).toBeVisible();
  await expect(page.getByTestId('energy')).not.toBeEmpty();
  await expect(page.getByTestId('availability')).not.toBeEmpty();
});

test('le choix de la période met à jour la synthèse', async ({ page }) => {
  await page.goto('/sites/SITE001');

  await page.getByTestId('period').selectOption('168');

  await expect(page.getByRole('heading', { name: /^Synthèse/ })).toHaveText('Synthèse 7 jours');
  await expect(page.getByTestId('step').locator('option[value="1m"]')).toHaveJSProperty(
    'disabled',
    true,
  );
});

test('le sélecteur de site change de page', async ({ page }) => {
  await page.goto('/sites/SITE001');

  await page.getByLabel('Site').selectOption('SITE005');

  await expect(page).toHaveURL(/\/sites\/SITE005$/);
  await expect(page.getByText('Toulouse, France · capacité 600 kW')).toBeVisible();
});

test('une perte réseau marque le capteur réseau en panne', async ({ page }) => {
  await page.goto('/sites/SITE003');

  await expect(page.getByTestId('sensor-network')).toContainText('En panne');
  await expect(page.getByTestId('sensor-consumption')).toContainText('Inconnu');
});

test('une panne du capteur de température est signalée', async ({ page }) => {
  await page.goto('/sites/SITE002');

  await expect(page.getByTestId('sensor-temperature')).toContainText('En panne');
  await expect(page.getByTestId('sensor-network')).toContainText('OK');
});

test('les alertes du site mènent à la liste filtrée', async ({ page }) => {
  await page.goto('/sites/SITE002');

  await page.getByTestId('all-alerts').click();

  await expect(page).toHaveURL(/\/alertes\?site=SITE002$/);
  await expect(page.getByTestId('site')).toHaveValue('SITE002');
  await expect(page.getByTestId('alert-row')).toHaveCount(2);
});

test('un site inconnu affiche une erreur', async ({ page }) => {
  await page.goto('/sites/SITE999');

  await expect(page.getByRole('alert')).toHaveText('Site introuvable ou API indisponible.');
});
