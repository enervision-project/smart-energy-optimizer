import { expect, test } from '@playwright/test';
import { mockCoreApi, signIn } from './core-api';

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test('une synthèse du parc en erreur est signalée sans bloquer la page', async ({ page }) => {
  await mockCoreApi(page, { '/api/v1/stats/summary': 500 });

  await page.goto('/parc');

  await expect(page.getByText('Synthèse du parc indisponible.')).toBeVisible();
  await expect(page.getByText('Aucune alerte dans la dernière heure.')).toBeVisible();
});

test('des alertes en erreur sont signalées', async ({ page }) => {
  await mockCoreApi(page, { '/api/v1/alerts': 503 });

  await page.goto('/alertes');

  await expect(page.getByRole('alert')).toContainText('Alertes indisponibles');
});

test('des prévisions en erreur sont signalées', async ({ page }) => {
  await mockCoreApi(page, { '/api/v1/sites/SITE001/predictions': 500 });

  await page.goto('/previsions');

  await expect(page.getByRole('alert')).toHaveText('Prévisions indisponibles.');
});

test('un site sans prévision publiée affiche un message', async ({ page }) => {
  await mockCoreApi(page);

  await page.goto('/previsions');

  await expect(page.getByTestId('no-forecast')).toBeVisible();
});

test('un compte sans site affiche un message', async ({ page }) => {
  await mockCoreApi(page, { '/api/v1/sites': [] });

  await page.goto('/sites');

  await expect(page.getByText('Aucun site n’est rattaché à votre compte.')).toBeVisible();
});

test('un site sans mesure reste consultable', async ({ page }) => {
  await mockCoreApi(page);

  await page.goto('/sites/SITE001');

  await expect(page.getByText('Paris, France · capacité 200 kW')).toBeVisible();
  await expect(page.getByTestId('sensor-network')).toContainText('Inconnu');
});
