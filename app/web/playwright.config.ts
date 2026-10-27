import { defineConfig, devices } from '@playwright/test';

const CI = !!process.env['CI'];

/**
 * Tests end-to-end du front, sans back-end :
 * - `mock` : configuration `development` (MockEnergyApi, connexion désactivée), contenu des pages ;
 * - `api` : configuration `production` (HttpEnergyApi), réponses de core-api simulées par `page.route`,
 *   pour la connexion JWT et les états d'erreur.
 */
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  // Les deux `ng serve` partagent le processeur avec les navigateurs.
  workers: CI ? 2 : undefined,
  expect: { timeout: 10_000 },
  reporter: CI
    ? [['github'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'fr-FR',
    timezoneId: 'Europe/Paris',
  },
  projects: [
    {
      name: 'mock',
      testDir: 'e2e/mock',
      use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:4200' },
    },
    {
      name: 'api',
      testDir: 'e2e/api',
      use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:4201' },
    },
  ],
  webServer: [
    {
      command: 'npx ng serve --configuration development --port 4200',
      url: 'http://localhost:4200',
      reuseExistingServer: !CI,
      timeout: 180_000,
    },
    {
      command: 'npx ng serve --configuration production --port 4201',
      url: 'http://localhost:4201',
      reuseExistingServer: !CI,
      timeout: 180_000,
    },
  ],
});
