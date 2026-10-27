# web — front EnerVision

Application Angular 22 (composants standalone, signals, zoneless) : vue du parc, détail d'un site, prévisions et alertes. Elle consomme l'API de [core-api](../../services/core-api/README.md).

La conception (architecture, connexion) est décrite dans la documentation MkDocs : [`docs/`](docs/index.md).

## Lancer en local

Deux modes, choisis par `environment.useMock` :

| Commande | Données | Connexion | Usage |
|---|---|---|---|
| `npm start` | Factices (`MockEnergyApi`) | Désactivée : pas de page de login, toutes les pages accessibles | Développer l'interface sans back |
| `npm run start:api` | Vraie API core-api sur `localhost:8080`, via [`proxy.conf.json`](proxy.conf.json) | Obligatoire | Tester contre le back : connexion, droits, vraies données |

Dans les deux cas, l'application est sur http://localhost:4200.

Pour `npm run start:api`, démarrer d'abord la base et core-api depuis la racine du dépôt :

```bash
# .env : JWT_SECRET (openssl rand -base64 32), ADMIN_EMAIL et ADMIN_PASSWORD (12 caractères minimum)
docker compose up -d --build core-api
```

Le compte `ADMIN_EMAIL` / `ADMIN_PASSWORD` est créé au démarrage de l'API si la table `users` est vide (voir [Premier compte](../../services/core-api/README.md#premier-compte)).

> En production, le front est servi par nginx (image `app/web/Dockerfile`) derrière Caddy, qui envoie `/api/*` à core-api sur le même domaine : pas de CORS, pas de proxy Angular.

## Commandes

```bash
npm test          # tests unitaires (Vitest)
npm run e2e       # tests end-to-end (Playwright, voir plus bas)
npm run lint      # ESLint
npm run format    # ESLint avec correction automatique
npx prettier --check src
npm run build     # build de production dans dist/web
```

La CI (`.github/workflows/ci.yml`) lance lint, tests, build et l'analyse SonarCloud à chaque PR qui modifie `app/web/`, et en parallèle les tests end-to-end.

### Tests end-to-end (Playwright)

`e2e/` contient deux projets, chacun avec son `ng serve` lancé par Playwright (`playwright.config.ts`) :

- `mock` (port 4200, configuration `development`) : contenu et navigation des pages sur les données de `MockEnergyApi` ;
- `api` (port 4201, configuration `production`) : connexion JWT, jeton envoyé à l'API, erreurs et états vides. Les réponses de core-api sont simulées dans le navigateur (`e2e/api/core-api.ts`), aucun back-end n'est nécessaire.

```bash
npx playwright install chromium   # une fois
npm run e2e
npx playwright show-report        # rapport HTML, traces des échecs
```

Sous WSL sans les bibliothèques système de Chromium, lancer les tests dans l'image officielle :

```bash
docker run --rm --ipc=host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/work -w /work \
  mcr.microsoft.com/playwright:v1.64.1-noble npm run e2e
```

En CI, le rapport et les traces sont publiés en artefact `playwright-report` uniquement en cas d'échec.

## Organisation du code

```text
src/app/
├── app.ts / app.html        coque : en-tête (utilisateur, déconnexion), menu, badge des alertes
├── app.routes.ts            routes ; toutes sauf /login passent par authGuard
├── app.config.ts            providers : routeur, HttpClient + authInterceptor, choix mock / HTTP
├── core/
│   ├── models/              interfaces des réponses de l'API (champs en camelCase, comme core-api)
│   ├── services/
│   │   ├── api.ts           préfixe des routes (/api/v1)
│   │   ├── energy-api.ts    contrat d'accès aux données (classe abstraite)
│   │   ├── http-energy-api.ts   implémentation HTTP (core-api)
│   │   ├── mock-energy-api.ts   implémentation factice (npm start)
│   │   └── auth.ts          session : jeton JWT, connexion, déconnexion, utilisateur courant
│   ├── interceptors/        authInterceptor : jeton sur les appels /api, 401 → page de connexion
│   ├── guards/              authGuard : pages réservées aux utilisateurs connectés
│   └── resources/           reloadOnError : relance un rxResource après une erreur
└── features/                une page par dossier (parc, site, previsions, alertes, login)
```

## Conventions

- **Accès aux données** : un composant injecte `EnergyApi`, jamais `HttpClient`. Toute nouvelle route se déclare dans `EnergyApi`, puis s'implémente dans `HttpEnergyApi` **et** `MockEnergyApi` (sinon `npm start` ne compile plus).
- **Chargement** : `rxResource` ; lire la valeur via `hasValue()` (un `value()` sur une ressource en erreur lève une exception). Pour un rafraîchissement périodique, `timer(0, N)` + `switchMap`, et `reloadOnError` pour que le rafraîchissement reprenne après un échec.
- **Connexion** : rien à faire dans les pages. L'intercepteur ajoute le jeton à tout appel commençant par `/api/v1` ; une nouvelle route est protégée par le guard dès qu'elle est déclarée dans les `children` de `app.routes.ts`.
- **Tests** : `TestBed` avec `MockEnergyApi` ou `provideHttpClientTesting()`. En test, l'environnement est celui de développement (`useMock: true`) : fournir `{ provide: AUTH_ENABLED, useValue: true }` pour tester un comportement lié à la connexion.
- **Textes** : interface et commentaires en français.
