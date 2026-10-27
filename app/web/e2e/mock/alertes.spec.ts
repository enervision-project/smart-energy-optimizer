import { expect, test } from '@playwright/test';

/**
 * Alertes de `MockEnergyApi` : 9 alertes, dont 7 dans la dernière heure (2 critiques, 1 élevée,
 * 3 moyennes, 1 faible), 2 pour SITE002 dont un pic, aucune pour SITE004.
 */

test.beforeEach(async ({ page }) => {
  await page.goto('/alertes');
});

test('liste les alertes de la dernière heure avec les compteurs', async ({ page }) => {
  await expect(page.getByTestId('alert-row')).toHaveCount(7);
  await expect(page.getByTestId('count-critical')).toContainText('2');
  await expect(page.getByTestId('count-high')).toContainText('1');
  await expect(page.getByTestId('count-medium')).toContainText('3');
  await expect(page.getByTestId('count-low')).toContainText('1');
});

test('un compteur filtre la liste, un second clic retire le filtre', async ({ page }) => {
  const critical = page.getByTestId('count-critical');

  await critical.click();
  await expect(critical).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('alert-row')).toHaveCount(2);

  await critical.click();
  await expect(page.getByTestId('alert-row')).toHaveCount(7);
});

test('filtre par site et par type', async ({ page }) => {
  await page.getByTestId('site').selectOption('SITE002');
  await expect(page.getByTestId('alert-row')).toHaveCount(2);

  await page.getByTestId('type').selectOption('spike');
  await expect(page.getByTestId('alert-row')).toHaveCount(1);
  await expect(page.getByTestId('alert-row')).toContainText('Pic de consommation détecté sur');
});

test('une période plus longue montre les alertes anciennes, grisées', async ({ page }) => {
  await page.getByTestId('period').selectOption('24');

  await expect(page.getByTestId('alert-row')).toHaveCount(9);
  await expect(page.locator('[data-testid="alert-row"].old')).toHaveCount(2);
});

test('un filtre sans résultat affiche un message', async ({ page }) => {
  await page.getByTestId('site').selectOption('SITE004');

  await expect(page.getByText('Aucune alerte sur la période.')).toBeVisible();
});
