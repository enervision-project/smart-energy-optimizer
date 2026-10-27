import { Page, Route } from '@playwright/test';

/** Jeton factice : le front ne le décode pas, il le renvoie tel quel dans `Authorization`. */
export const TOKEN = 'e2e-token';

const SITE = {
  siteId: 'SITE001',
  siteType: 'office',
  siteName: 'Bureau Paris La Défense',
  location: 'Paris, France',
  capacityKw: 200,
  status: 'active',
};

const USER = {
  id: '1',
  email: 'pilote@enervision.test',
  firstName: 'Camille',
  lastName: 'Martin',
  companyName: 'EnerVision',
  role: 'USER',
};

/** Réponses de core-api par défaut, assez complètes pour que chaque page s'affiche. */
function defaultResponse(path: string): unknown {
  const now = new Date().toISOString();
  if (path === '/api/v1/users/me') return USER;
  if (path === '/api/v1/sites') return [SITE];
  if (path === `/api/v1/sites/${SITE.siteId}`) return SITE;
  if (path === '/api/v1/stats/summary') {
    return {
      timestamp: now,
      totalSites: 1,
      totalConsumptionKw: 120,
      totalCapacityKw: 200,
      averageLoadPercent: 60,
      sitesWithoutData: [],
      sites: [
        {
          siteId: SITE.siteId,
          siteName: SITE.siteName,
          currentConsumptionKw: 120,
          consumptionImputed: false,
          capacityKw: 200,
          loadPercent: 60,
          dataQuality: 'good',
          ts: now,
          ageSeconds: 30,
        },
      ],
    };
  }
  if (path.endsWith('/readings') || path.endsWith('/predictions')) {
    return { siteId: SITE.siteId, step: '1h', from: now, to: now, points: [] };
  }
  if (path === '/api/v1/alerts') {
    return { content: [], page: { size: 20, number: 0, totalElements: 0, totalPages: 0 } };
  }
  if (path === '/api/v1/alerts/summary') {
    return { since: now, total: 0, bySeverity: { low: 0, medium: 0, high: 0, critical: 0 } };
  }
  // /readings/latest, /readings/summary, /recommendations : pas de contenu
  return null;
}

/** Remplacements de réponses par chemin exact, par exemple `{ '/api/v1/stats/summary': 500 }`. */
export type Overrides = Record<string, number | unknown>;

/**
 * Simule core-api derrière `/api/v1` et note l'en-tête `Authorization` de chaque appel.
 * Un nombre en override renvoie ce statut HTTP sans contenu.
 */
export async function mockCoreApi(page: Page, overrides: Overrides = {}): Promise<string[]> {
  const authorizations: string[] = [];
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/auth/login') {
      return route.fallback();
    }
    authorizations.push(request.headers()['authorization'] ?? '');
    const override = overrides[path];
    if (typeof override === 'number') {
      return route.fulfill({ status: override });
    }
    const body = path in overrides ? override : defaultResponse(path);
    return body === null ? route.fulfill({ status: 204 }) : route.fulfill({ json: body });
  });
  return authorizations;
}

/** Réponse de POST /api/v1/auth/login : jeton valide une heure, ou statut d'erreur. */
export async function mockLogin(page: Page, status = 200): Promise<void> {
  await page.route('**/api/v1/auth/login', (route) =>
    status === 200
      ? route.fulfill({ json: { accessToken: TOKEN, tokenType: 'Bearer', expiresIn: 3600 } })
      : route.fulfill({ status }),
  );
}

/** Ouvre la session avant le chargement de la page, comme après une connexion réussie. */
export async function signIn(page: Page): Promise<void> {
  await page.addInitScript((token) => {
    sessionStorage.setItem(
      'enervision.session',
      JSON.stringify({ token, expiresAt: Date.now() + 3_600_000 }),
    );
  }, TOKEN);
}
