# core-api

API principale d'Enervision, construite comme un **monolithe modulaire** Spring Boot 4 / Java 21 avec Maven multi-modules.

Un seul processus est déployé, mais le code est découpé en modules métier indépendants, chacun dans son propre module Maven. Voir aussi l'[architecture applicative globale](../../docs/doc-technique/architecture-applicative.md).

## Architecture

```mermaid
flowchart TD
    APP("application<br/><i>point d'entrée Spring Boot</i>")
    USER("user")
    DIAG("diagnostic")
    TELEM("telemetry")
    CONF("configuration")

    APP --> USER
    APP --> DIAG
    APP --> TELEM
    APP --> CONF
```

| Module          | Rôle                                                        | Package racine               |
|-----------------|-------------------------------------------------------------|------------------------------|
| `application`   | Assemble les modules, contient la classe `main` et la config | `com.enervision`             |
| `user`          | Gestion des utilisateurs                                    | `com.enervision.user`        |
| `diagnostic`    | Alertes et recommandations                                  | `com.enervision.diagnostic`  |
| `telemetry`     | Données de télémétrie (appels au ML-service via RestClient) | `com.enervision.telemetry`   |
| `configuration` | Configuration fonctionnelle de la plateforme                | `com.enervision.configuration` |

### Structure Maven

```
core-api/                  pom parent (packaging pom)
├── pom.xml
├── Dockerfile             image de l'API (contexte = racine du dépôt)
├── application/           jar exécutable (spring-boot-maven-plugin)
├── user/                  jar simple
├── diagnostic/            jar simple
├── telemetry/             jar simple
└── configuration/         jar simple
```

- **`pom.xml` (parent)** : hérite de `spring-boot-starter-parent`, déclare les modules, gère les versions des modules internes et de springdoc dans `<dependencyManagement>`, et configure Lombok pour tous les modules.
- **Modules métier** : héritent de `core-api` et produisent un jar classique. Ils ne déclarent **pas** `spring-boot-maven-plugin` (un jar repackagé n'est pas utilisable comme dépendance).
- **`application`** : dépend de tous les modules métier, porte les dépendances runtime (PostgreSQL, DevTools) et produit le jar exécutable final.

### Règles à respecter

- **Versions** : ne pas redéclarer dans `<dependencyManagement>` une dépendance déjà gérée par Spring Boot (starters, Lombok, PostgreSQL…). Une entrée sans version écrase celle du parent et casse le build (`version is missing`).
- **Packages** : tout le code d'un module doit être sous `com.enervision.<module>`. La classe `Application` est dans `com.enervision`, ce qui permet au scan des composants et des entités JPA de trouver tous les modules.
- **Configuration** : un seul `application.yaml`, dans `application/src/main/resources`. Les modules métier ne doivent pas en avoir (un seul serait chargé sur le classpath).
- **Dépendances entre modules** : un module métier ne dépend pas d'`application`. Si un module doit en utiliser un autre, déclarer la dépendance dans son `pom.xml` et éviter les cycles.

## Base de données

core-api utilise la base TimescaleDB (PostgreSQL 16) du service `db`, défini dans le [`compose.yaml` racine](../../compose.yaml).

- **Schéma** : géré par [`infra/db/init.sql`](../../infra/db/init.sql), exécuté uniquement au premier démarrage du conteneur (volume vide). Hibernate est en `ddl-auto: validate` : il ne crée ni ne modifie aucune table, il vérifie seulement que les entités JPA correspondent au schéma. Toute évolution du schéma passe donc par `init.sql`, puis par une recréation du volume (`docker compose down -v`).
- **Connexion** : via les variables `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME` et `SPRING_DATASOURCE_PASSWORD`, lues directement par Spring Boot. `application.yaml` ne contient aucune valeur par défaut : en conteneur, `compose.yaml` les fournit ; en local, le `.env` racine (voir [Configuration et secrets](#configuration-et-secrets)).

## Build et exécution

Prérequis : Java 21, Docker avec les plugins Compose v2 et Buildx (le Dockerfile utilise un cache BuildKit). Les commandes `docker compose` se lancent depuis la racine du dépôt, après `cp .env.example .env`.

### Dev local (app lancée depuis l'IDE ou Maven)

```bash
# Depuis la racine du dépôt : démarrer uniquement la base
docker compose up -d db

# Depuis services/core-api : construire puis lancer l'application
./mvnw clean package -DskipTests
java -jar application/target/application-0.0.1-SNAPSHOT.jar
```

L'application lit automatiquement le `.env` racine (`spring.config.import: optional:file:../../.env[.properties]`), à condition d'être lancée **depuis `services/core-api`**. Dans l'IDE, le répertoire de travail de la configuration de lancement doit donc être `services/core-api`. Sinon le `.env` n'est pas trouvé, et l'application refuse de démarrer avec un message indiquant la propriété manquante.

### Stack complète en conteneurs

```bash
# Depuis la racine du dépôt
docker compose up --build
```

L'API est alors disponible sur http://localhost:8080. Le service `core-api` attend que `db` soit healthy, puis s'y connecte via le réseau Compose (hôte `db`), avec les identifiants `POSTGRES_*` du `.env`. `JWT_SECRET` doit être renseigné dans le `.env` : sinon `docker compose` refuse de démarrer.

L'image est construite par [`Dockerfile`](Dockerfile), avec la racine du dépôt comme contexte (même convention que `etl-worker`) : une étape Maven produit le jar, puis une image JRE 21 seule l'exécute.

### Maven

```bash
# Compiler tous les modules
./mvnw clean compile

# Construire le jar exécutable (sans les tests)
./mvnw clean package -DskipTests

# Lancer le jar
java -jar application/target/application-0.0.1-SNAPSHOT.jar
```

## Sécurité

Authentification **stateless par jeton JWT** (Bearer, signé en HS256), avec Spring Security en resource server.

| Où | Quoi |
|---|---|
| `application` — `com.enervision.config.SecurityConfig` | Règles communes à tous les modules : tout endpoint exige un jeton valide, sauf les routes publiques (login, register, doc OpenAPI). Active `@PreAuthorize` et déclare le schéma Bearer dans la doc OpenAPI. |
| `user` — `com.enervision.user.security` | Fournisseur d'identité : émission des jetons (`TokenService`), vérification (`JwtDecoder`), conversion des rôles, hash des mots de passe (BCrypt), chargement des utilisateurs pour le login. |

### Endpoints

| Méthode | Route | Accès |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Public : crée un compte avec le rôle `USER` |
| `POST` | `/api/v1/auth/login` | Public : renvoie `{ accessToken, tokenType, expiresIn }` |
| `GET` | `/api/v1/users/me` | Connecté |
| `GET` | `/api/v1/users`, `/api/v1/users/{userId}` | `ADMIN` |
| `PATCH` | `/api/v1/users/{userId}/role` | `ADMIN` |

Les appels authentifiés envoient l'en-tête `Authorization: Bearer <accessToken>`. Le jeton contient l'id de l'utilisateur (`sub`), son email et ses rôles (`roles`). La doc interactive est sur http://localhost:8080/swagger-ui.html (bouton « Authorize »).

### Rôles

`USER` et `ADMIN`, exposés à Spring Security sous la forme `ROLE_USER` / `ROLE_ADMIN`. Pour restreindre un endpoint aux administrateurs, utiliser la méta-annotation `@AdminOnly` (`com.enervision.user.security`) plutôt qu'un `@PreAuthorize("hasRole('ADMIN')")` écrit à la main :

```java
@AdminOnly
@GetMapping
public List<SiteResponse> getSites() { … }
```

Une route publique se déclare dans `SecurityConfig` (module `application`).

> **Premier ADMIN** : l'inscription donne toujours le rôle `USER`. Pour l'instant, le premier administrateur se crée en changeant le rôle directement en base (`UPDATE users SET role = 'ADMIN' WHERE email = '…'`).

## Configuration et secrets

**Aucun secret n'est versionné.** `application.yaml` ne contient que des valeurs non sensibles ; les secrets n'ont pas de valeur par défaut, et l'application refuse de démarrer s'ils manquent (message explicite au démarrage).

| Variable | Secret | Défaut | Rôle |
|---|---|---|---|
| `SPRING_DATASOURCE_URL` | Non | aucun | URL JDBC de la base |
| `SPRING_DATASOURCE_USERNAME` | Non | aucun | Utilisateur de la base |
| `SPRING_DATASOURCE_PASSWORD` | **Oui** | aucun | Mot de passe de la base |
| `JWT_SECRET` | **Oui** | aucun | Clé HMAC encodée en Base64, 32 octets minimum (`openssl rand -base64 32`). Une clé différente par environnement. |
| `JWT_EXPIRATION` | Non | `1h` | Durée de validité d'un jeton |

Où vivent les valeurs selon l'environnement :

| Environnement | Source | Versionné ? |
|---|---|---|
| Dev local (IDE, `java -jar`) | `.env` à la racine du dépôt, créé à partir de `.env.example`, importé par Spring au démarrage | Non (gitignoré, exclu des images Docker) |
| Stack Compose | Même `.env` ; `compose.yaml` passe les variables au conteneur (avec l'hôte `db` pour la base) | Non (gitignoré) |
| CI / déploiement | Secrets de la plateforme (ex. GitHub Secrets transmis par le workflow de déploiement), injectés en variables d'environnement | Non |

## Tests

```bash
./mvnw clean verify
```

> **Note** : aucune base de données n'est encore configurée. Le démarrage et le test `ApplicationTests.contextLoads` échouent tant que `spring.datasource.*` n'est pas renseigné (PostgreSQL via `compose.yaml` ou Testcontainers).

## Ajouter un module

1. Créer le dossier `<module>/` avec un `pom.xml` qui a `core-api` comme parent.
2. L'ajouter dans `<modules>` et dans `<dependencyManagement>` du `pom.xml` parent.
3. L'ajouter comme dépendance dans `application/pom.xml`.
4. Placer le code sous `com.enervision.<module>`.

## Références

- [Spring Boot 4.1.1](https://docs.spring.io/spring-boot/4.1.1/)
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/4.1.1/maven-plugin)
- [Maven multi-modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [SpringDoc OpenAPI](https://springdoc.org/)
