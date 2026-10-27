import { expect, test } from '@playwright/test';

test('affiche la prévision du premier site par défaut', async ({ page }) => {
  await page.goto('/previsions');

  await expect(page.getByTestId('site')).toHaveValue('SITE001');
  await expect(page.getByText('capacité 200 kW · horizon H+24')).toBeVisible();
  await expect(page.getByTestId('peak')).toContainText('kW');
  await expect(page.getByTestId('energy')).toContainText('kWh');
  await expect(page.getByTestId('model')).toContainText('enervision-hourly-consumption');
  await expect(page.locator('canvas[aria-label$="prévue sur 24 heures"]')).toBeVisible();
});

test('le choix du site est conservé dans l’adresse', async ({ page }) => {
  await page.goto('/previsions');

  await page.getByTestId('site').selectOption('SITE004');

  await expect(page).toHaveURL(/\/previsions\?site=SITE004$/);
  await expect(page.getByText('capacité 400 kW · horizon H+24')).toBeVisible();
});
