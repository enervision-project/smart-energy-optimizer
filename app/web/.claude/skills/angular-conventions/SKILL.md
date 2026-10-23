---
name: angular-conventions
description: Conventions de code et architecture du front EnerVision (Angular 22, composants standalone, signals, zoneless, Vitest). À charger avant d'écrire, modifier ou relire du code dans app/web — nouvelle page, composant, appel à l'API, modèle, mock, style ou test.
---

# Conventions Angular — front EnerVision

Application Angular 22 sans NgModule ni zone.js : composants standalone, signals, `rxResource`. Voir `README.md` pour les commandes et les modes de lancement (mock ou vraie API).

## 1. Organisation

```
src/app/
├── app.ts / app.html / app.routes.ts / app.config.ts   coque, routes, providers
├── core/          code transverse, sans interface visuelle
│   ├── models/        interfaces des réponses de l'API
│   ├── services/      api.ts (API_BASE_URL), EnergyApi (contrat) + HttpEnergyApi + MockEnergyApi, auth.ts (session)
│   ├── resources/     helpers pour rxResource (reloadOnError)
│   ├── guards/        authGuard
│   └── interceptors/  authInterceptor
├── shared/components/ composants réutilisés par plusieurs pages (kpi-card, consumption-chart…)
└── features/<page>/   une page par dossier : alertes, parc, site, previsions, login
    ├── <page>.ts / .html / .scss / .spec.ts
    ├── <sous-composant>/          composant propre à la page (ex. site/site-alerts)
    └── <logique>.ts               fonctions pures de la page (ex. site/reading-summary.ts)
```

- Un composant utilisé par une seule page reste dans le dossier de cette page ; il passe dans `shared/` dès qu'une deuxième page en a besoin.
- Nommage des fichiers sans suffixe de type (`site.ts`, classe `Site` ; `site-alerts.ts`, classe `SiteAlerts`), comme le génère Angular 22.

## 2. Accès aux données

```
Composant → EnergyApi (classe abstraite) → HttpEnergyApi (core-api)  |  MockEnergyApi (npm start)
```

- Un composant injecte **`EnergyApi`**, jamais `HttpClient`. L'implémentation est choisie dans `app.config.ts` selon `environment.useMock`.
- Nouvelle route : la déclarer dans `EnergyApi` (avec un commentaire si le sens d'un paramètre n'est pas évident), puis l'implémenter dans `HttpEnergyApi` **et** `MockEnergyApi`, sinon `npm start` ne compile plus.
- `HttpEnergyApi` : URL construites à partir de `API_BASE_URL` (`core/services/api.ts`, `/api/v1`, même domaine, pas de CORS) ; paramètres de requête avec `HttpParams` ou un objet `params`, dates en `toISOString()`.
- `MockEnergyApi` : reproduit la forme et le comportement de l'API (pagination, filtres, erreur « Site inconnu » via `throwError`), avec des données **déterministes et datées par rapport à maintenant**, pour que les tests puissent compter des lignes. Documenter ce que contient le mock en tête de fichier et dans les specs qui s'en servent.

## 3. Modèles

- `interface` dans `core/models/`, une par réponse ; noms de champs **identiques au JSON** de l'API : camelCase pour core-api (`siteId`, `capacityKw`), snake_case pour les routes encore calquées sur l'API Mock (`Reading.consumption_kw`). Pas de mapping côté front.
- Valeurs fermées : tableau `as const` + type dérivé (`ALERT_SEVERITIES`, `AlertSeverity`). Si la base peut renvoyer une valeur hors liste, garder le champ en `string` et prévoir un affichage par défaut (voir `alert-labels.ts`).
- Une mesure absente reste `null` : on l'affiche comme un trou ou « — », on ne la filtre jamais.
- Constantes partagées liées au modèle à côté de lui (ex. `ALERT_REFRESH_MS` dans `alert.ts`).

## 4. Composants

```ts
@Component({
  imports: [RouterLink],
  selector: 'app-site-alerts',
  styleUrl: './site-alerts.scss',
  templateUrl: './site-alerts.html',
})
export class SiteAlerts {
  private readonly api = inject(EnergyApi);

  readonly siteId = input.required<string>();

  protected readonly alerts = rxResource({
    params: () => this.siteId(),
    stream: ({ params: siteId }) => this.api.getAlerts({ siteId }, 0, 10),
  });

  /** `value()` lève une erreur quand la ressource est en échec : on passe par `hasValue()`. */
  protected readonly alertPage = computed(() =>
    this.alerts.hasValue() ? this.alerts.value() : undefined,
  );
}
```

- Standalone (pas de `standalone: true`, c'est le défaut), sélecteur préfixé `app-` en kebab-case, template et styles dans des fichiers séparés.
- Injection avec `inject()` dans un champ `private readonly`, pas de constructeur d'injection. Le constructeur ne sert qu'aux `effect` et à `reloadOnError`.
- État en **signals** : `input()` / `input.required()` pour les entrées, `signal` pour l'état local, `computed` pour le dérivé, `linkedSignal` pour un état qui se réinitialise quand une source change (ex. page remise à 0 quand un filtre change). Pas de `@Input()`, `@Output()`, `BehaviorSubject` ni `subscribe` manuel dans un composant.
- Chargement avec `rxResource` ; lire la valeur via `hasValue()` (un `value()` sur une ressource en erreur lève une exception). Erreur : `resource.error()` dans le template.
- Rafraîchissement périodique : `timer(0, N).pipe(switchMap(...))` dans le `stream`, plus `reloadOnError(resource, N)` dans le constructeur, sans quoi le flux s'arrête au premier échec.
- Membres utilisés par le template : `protected` ; le reste `private`. Les fonctions de libellés importées s'exposent en champ (`protected readonly severityLabel = severityLabel`).
- Formatage avec `Intl.NumberFormat` / `Intl.DateTimeFormat('fr-FR', …)` en constantes de module, pas de pipes de date ou de nombre.
- Logique de calcul non triviale : fonction pure dans un fichier à part, testable sans TestBed (ex. `summarize` dans `reading-summary.ts`).

## 5. Templates

- Control flow intégré : `@if`, `@else if`, `@for (… ; track id)`, `@if (x(); as v)`. Pas de `*ngIf` / `*ngFor`.
- Chaque bloc de données gère trois états : erreur (`<p class="error" role="alert">`), chargement (« Chargement… ») et vide (« Aucune … »).
- Accessibilité (vérifiée par `templateAccessibility` d'ESLint) : `aria-labelledby` vers le titre de la section, `aria-label` sur un graphique ou une liste sans titre, `aria-pressed` sur un bouton bascule, `<th scope="col">`.
- `data-testid` sur les éléments que les tests ciblent (lignes, compteurs, liens) plutôt que des classes CSS.

## 6. Routage

- Routes dans `app.routes.ts`, pages chargées à la demande avec `loadComponent`. Chemins en français (`/alertes`, `/sites/:id`, `/previsions`).
- `withComponentInputBinding()` est actif : paramètres de route **et** de requête arrivent en `input()` du composant de page (`id` pour `/sites/:id`, `site` pour `/alertes?site=`). Pour un filtre initialisé depuis l'URL mais modifiable : `linkedSignal(() => this.site() ?? '')`.
- Liens : `[routerLink]` (et `[queryParams]`) ; navigation programmatique avec `Router.navigate`.

## 7. Connexion

- Jeton JWT de core-api, géré par le service `Auth` (`core/services/auth.ts`) et conservé dans le `sessionStorage`. Une page ne lit jamais le jeton.
- `authInterceptor` ajoute `Authorization: Bearer …` à tout appel commençant par `API_BASE_URL` ; sur un 401, il ferme la session et renvoie vers `/login?returnUrl=…`. Une nouvelle route d'API n'a donc rien à faire pour être authentifiée.
- `authGuard` protège toutes les routes déclarées dans les `children` de la route `''` (`canActivateChild`) : une nouvelle page s'ajoute **dans ces `children`**, jamais à côté de `login`.
- `AUTH_ENABLED` vaut `!environment.useMock` : en mode mock (`npm start`), pas de page de connexion ni de jeton.
- Droits : le back filtre déjà les données (sites visibles, `@AdminOnly`) ; le front se contente de gérer proprement le 403/404 comme une erreur.

## 8. Styles

- SCSS par composant, encapsulé ; `styles.scss` global reste minimal.
- Palette actuelle (en dur dans les composants) : texte `#1f2a37`, texte secondaire `#5b6573`, bordures `#dde2da` / `#c8cfc4`, accent `#1f7a63`, erreur `#b23a48` sur `#fbeaec`. Cartes : `padding: 16px 20px`, `border-radius: 10px`, fond blanc.
- Couleurs de sévérité via les variables `--sev-bg` / `--sev-fg` posées par les classes `low`, `medium`, `high`, `critical`.
- Mise en page en grid / flex avec un passage en une colonne sous 900 px ; tableaux dans un conteneur `overflow-x: auto`.
- Budget de build : 500 kB d'avertissement pour le bundle initial, 4 kB par fichier de style de composant.

## 9. Langue et format

- **Interface, commentaires et noms de tests en français** ; identifiants (classes, variables, fonctions) en anglais. Les routes de pages sont en français.
- Prettier : `printWidth` 100, quotes simples. ESLint : `angular-eslint` (TS + templates) et `typescript-eslint` stylistic.
- Commentaires JSDoc (`/** … */`) courts, pour expliquer un choix ou une contrainte de l'API, pas pour paraphraser le code.

## 10. Tests

| Cible | Approche |
|---|---|
| Page ou composant | `TestBed` avec `{ provide: EnergyApi, useValue: new MockEnergyApi() }` et `provideRouter([])` ; `vi.spyOn(api, …)` pour forcer un cas (`of(...)` vide, `throwError`) |
| Appels HTTP | `provideHttpClient()` + `provideHttpClientTesting()`, `HttpTestingController` |
| Fonction pure | Test direct, sans TestBed |
| Composant avec graphique | `provideCharts(withDefaultRegisterables())` |

- En test, l'environnement est celui de développement (`useMock: true`, donc `AUTH_ENABLED` faux) : fournir `{ provide: AUTH_ENABLED, useValue: true }` pour tester un comportement lié à la connexion.
- Vitest (globals `describe`, `it`, `expect`, `vi`), environnement jsdom ; le message « HTMLCanvasElement's getContext() » est normal.
- Entrées : `fixture.componentRef.setInput('siteId', 'SITE001')`, puis `await fixture.whenStable()`.
- Rafraîchissement périodique : `vi.useFakeTimers()`, `fixture.detectChanges()` puis `vi.advanceTimersByTimeAsync(ms)` (`whenStable()` attend des timers réels) ; `vi.useRealTimers()` dans `afterEach`.
- On teste ce que voit l'utilisateur (texte, nombre de lignes, `href`, `aria-*`) via `data-testid`, pas l'état interne.
- Noms en français décrivant le comportement : `it('grise les alertes de plus d’une heure', …)`.

## 11. Avant de terminer une tâche

```bash
npm test -- --watch=false
npm run lint
npx prettier --check src
npm run build
```

1. Les quatre commandes passent (la CI lance lint, tests, build et SonarCloud sur toute PR qui touche `app/web/`).
2. Toute méthode ajoutée à `EnergyApi` existe dans `HttpEnergyApi` et `MockEnergyApi`, et la route existe côté core-api (sinon le signaler).
3. Une nouvelle page est dans les `children` protégés de `app.routes.ts`, et testée avec la vraie API via `npm run start:api` (core-api lancé avec `docker compose up -d --build core-api`, connexion avec `ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`).
4. Les états erreur, chargement et vide sont gérés, et testés au moins pour l'erreur.
5. `README.md` et `docs/` mis à jour si l'organisation ou les commandes changent.
