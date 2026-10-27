import { expect, test } from '@playwright/test';

test('la racine ouvre la vue du parc', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL(/\/parc$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Vue d’ensemble du parc');
});

test('le menu mène à chaque page', async ({ page }) => {
  await page.goto('/parc');
  const nav = page.getByRole('navigation', { name: 'Navigation principale' });

  await nav.getByRole('link', { name: 'Sites' }).click();
  await expect(page).toHaveURL(/\/sites\/SITE001$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Détail d’un site');

  await nav.getByRole('link', { name: 'Prévisions' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Prévisions');

  await nav.getByRole('link', { name: /^Alertes/ }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Alertes');

  await nav.getByRole('link', { name: 'Vue du parc' }).click();
  await expect(page).toHaveURL(/\/parc$/);
});

test('une adresse inconnue renvoie vers le parc', async ({ page }) => {
  await page.goto('/inconnue');

  await expect(page).toHaveURL(/\/parc$/);
});

test('le badge du menu compte les alertes de la dernière heure', async ({ page }) => {
  await page.goto('/parc');

  await expect(page.getByTestId('alert-badge')).toHaveText('7');
});

test('sans back-end, la page de connexion renvoie vers l’application', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByText('Connexion désactivée')).toBeVisible();
  await expect(page.getByTestId('logout')).toHaveCount(0);
});
