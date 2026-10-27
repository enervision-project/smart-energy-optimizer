import { expect, test } from '@playwright/test';
import { TOKEN, mockCoreApi, mockLogin, signIn } from './core-api';

test('sans session, une page renvoie vers la connexion', async ({ page }) => {
  await mockCoreApi(page);

  await page.goto('/alertes');

  await expect(page).toHaveURL(/\/login\?returnUrl=%2Falertes$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Connexion');
});

test('la connexion ramène à la page demandée et envoie le jeton à l’API', async ({ page }) => {
  const authorizations = await mockCoreApi(page);
  await mockLogin(page);
  await page.goto('/alertes');

  await page.getByTestId('email').fill('pilote@enervision.test');
  await page.getByTestId('password').fill('secret');
  await page.getByTestId('submit').click();

  await expect(page).toHaveURL(/\/alertes$/);
  await expect(page.getByTestId('user-name')).toHaveText('Camille Martin');
  expect(authorizations.length).toBeGreaterThan(0);
  expect(authorizations.every((header) => header === `Bearer ${TOKEN}`)).toBe(true);
});

test('des identifiants refusés affichent un message', async ({ page }) => {
  await mockCoreApi(page);
  await mockLogin(page, 401);
  await page.goto('/login');

  await page.getByTestId('email').fill('pilote@enervision.test');
  await page.getByTestId('password').fill('mauvais');
  await page.getByTestId('submit').click();

  await expect(page.getByRole('alert')).toHaveText('Email ou mot de passe incorrect.');
  await expect(page).toHaveURL(/\/login$/);
});

test('une API injoignable à la connexion affiche un message', async ({ page }) => {
  await mockCoreApi(page);
  await mockLogin(page, 502);
  await page.goto('/login');

  await page.getByTestId('email').fill('pilote@enervision.test');
  await page.getByTestId('password').fill('secret');
  await page.getByTestId('submit').click();

  await expect(page.getByRole('alert')).toContainText('API injoignable');
});

test('un formulaire vide n’est pas envoyé', async ({ page }) => {
  await mockCoreApi(page);
  await page.goto('/login');

  await page.getByTestId('submit').click();

  await expect(page.getByText('Saisissez une adresse email valide.')).toBeVisible();
  await expect(page.getByText('Saisissez votre mot de passe.')).toBeVisible();
});

test('un jeton refusé par l’API ferme la session', async ({ page }) => {
  await signIn(page);
  await mockCoreApi(page, { '/api/v1/stats/summary': 401 });

  await page.goto('/parc');

  await expect(page).toHaveURL(/\/login\?returnUrl=%2Fparc$/);
});

test('la déconnexion ramène à la page de connexion', async ({ page }) => {
  await signIn(page);
  await mockCoreApi(page);
  await page.goto('/parc');

  await page.getByTestId('logout').click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByTestId('logout')).toHaveCount(0);
});
