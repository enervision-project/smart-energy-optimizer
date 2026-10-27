# Architecture applicative

```mermaid
flowchart LR
    USER("👤 Utilisateur")
    MOCK("API Mock<br/>(école)")

    subgraph APP["EC2 enervision-app"]
        direction LR
        PROXY("proxy<br/>Caddy HTTPS")
        WEB("web<br/>Angular + nginx")

        subgraph CORE["core-api"]
            direction TB
            U("user") ~~~ C("configuration") ~~~ D("diagnostic") ~~~ T("telemetry")
        end

        ETL("scheduler<br/>ETL Python, cron")
        DB[("db<br/>TimescaleDB")]
        JOBS("prediction-jobs<br/>entraînement, prévisions")
        PRED("prediction-service<br/>API /predict")
        MLFLOW("mlflow<br/>Model Registry")
        ALLOY("alloy")
    end

    S3[("S3<br/>bronze, artefacts,<br/>Parquet ML")]
    MON("EC2 monitoring<br/>Prometheus, Loki, Grafana")

    USER -->|HTTPS| PROXY
    PROXY -->|/| WEB
    PROXY -->|/api/*| CORE
    CORE --> DB
    MOCK --> ETL
    ETL --> DB
    ETL -->|JSON brut| S3
    DB -->|readings_hours| JOBS
    JOBS -->|predictions| DB
    S3 -->|Parquet| JOBS
    JOBS <--> MLFLOW
    MLFLOW <--> S3
    MLFLOW --> PRED
    ALLOY -->|métriques, logs| MON
```

## Composants

| Composant | Rôle | Doc |
|---|---|---|
| `proxy` | Caddy, seul point d'entrée public. HTTPS automatique, `/api/*` vers core-api, le reste vers le front | [Déploiement](infra/deploiement.md) |
| `web` | Front Angular servi par nginx. Ne parle qu'à core-api | UI |
| `core-api` | API REST Spring Boot, monolithe modulaire : comptes et JWT (`user`), sites (`configuration`), alertes et recommandations (`diagnostic`), mesures et prévisions (`telemetry`) | Core API |
| `scheduler` | ETL Python lancé par cron : collecte chaque minute, rattrapage et agrégats chaque heure, sites chaque jour | ETL Worker |
| `db` | PostgreSQL 16 + TimescaleDB. Schéma géré par Liquibase (service `migrate`) | [Modèle de données](modele-de-donnees.md) |
| `prediction-jobs` | Réentraîne le modèle chaque nuit, publie chaque heure une prévision sur 24 h | Prediction Service |
| `prediction-service` | Sert le modèle champion (`/predict`). Interne, jamais exposé | Prediction Service |
| `mlflow` | Suivi des entraînements et registre des modèles (alias `champion`) | ML Service |
| `alloy` | Pousse métriques et logs vers l'EC2 de monitoring | [Monitoring](infra/monitoring.md) |

Le **ML Service** n'est pas un conteneur de production : c'est l'outillage hors ligne (notebooks, campagnes d'essais) qui a permis de choisir le modèle.

## Flux principaux

1. **Collecte** : chaque minute, l'ETL lit `/current` de l'API Mock pour chaque site, archive le JSON brut dans S3 puis l'écrit dans `readings_raws`. Les minutes manquées sont rattrapées chaque heure via `/readings`.
2. **Agrégation** : chaque heure, l'ETL calcule `readings_hours` à partir des mesures brutes.
3. **Prévision** : chaque heure à :05, `prediction-jobs` calcule 24 h de prévisions avec le champion et les écrit dans `predictions`.
4. **Consultation** : le front appelle core-api avec un jeton JWT. core-api lit la base et ne renvoie que les sites visibles par l'utilisateur.

core-api ne dépend ni de l'ETL ni du ML : tout passe par la base. Un service arrêté n'empêche pas les autres de tourner.
