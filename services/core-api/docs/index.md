# Core API

API principale d'EnerVision : un **monolithe modulaire** Spring Boot 4 / Java 21. Un seul processus est déployé, mais le code est découpé en modules Maven indépendants. Le [README du service](https://github.com/enervision-project/smart-energy-optimizer/blob/main/services/core-api/README.md) détaille la structure Maven, le build, la configuration et les tests.

## Modules

```mermaid
flowchart TD
    APP("bootstrap<br/><i>main, SecurityConfig</i>")
    USER("user<br/><i>comptes, connexion, JWT</i>")
    CONF("configuration<br/><i>sites, profils, visibilité</i>")
    DIAG("diagnostic<br/><i>alertes</i>")
    TELEM("telemetry<br/><i>mesures (à venir)</i>")
    COMMON("common<br/><i>CurrentUser, Role, @AdminOnly</i>")

    APP --> USER & CONF & DIAG & TELEM
    DIAG -->|sites visibles| CONF
    USER & CONF & DIAG & TELEM --> COMMON
```

| Module | Endpoints | Documentation |
|---|---|---|
| `user` | `POST /api/v1/auth/login`, `/api/v1/users/**` | [Sécurité](securite.md) |
| `configuration` | `/api/v1/sites/**` | [Sécurité › visibilité des sites](securite.md#visibilite-des-sites) |
| `diagnostic` | `/api/v1/alerts/**` | [Alertes](alertes.md) |
| `telemetry` | (à venir) | — |

La documentation interactive des endpoints (Swagger UI) est disponible en local sur http://localhost:8080/swagger-ui.html ; elle est désactivée en production.

## Données

core-api lit la base TimescaleDB alimentée par l'ETL (`sites`, `site_profiles`, `alerts`, mesures) et ne gère lui-même que les comptes (`users`, `users_sites`). Le schéma est géré par Liquibase (`infra/db/changelog/`) ; Hibernate se contente de le valider au démarrage.

## Requête type

```mermaid
sequenceDiagram
    participant F as Front
    participant S as Spring Security
    participant C as Controller
    participant SV as Service du module
    participant SS as SiteService
    participant DB as Base

    F->>S: GET /api/v1/alerts<br/>Authorization: Bearer <jeton>
    S->>S: vérifie signature, émetteur, expiration
    S->>C: CurrentUser (id, rôle)
    C->>SV: getAlerts(user, filtres)
    SV->>SS: getSites(user)
    SS-->>SV: sites visibles
    SV->>DB: alertes de ces sites uniquement
    DB-->>F: page d'alertes (JSON)
```
