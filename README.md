# EnerVision · Smart Energy Optimizer

Suivi, prévision et optimisation de la consommation électrique d'un parc de sites.

Toutes les minutes, les mesures des sites sont collectées. Un modèle prévoit les 24 prochaines heures, et une application web affiche consommation, prévisions, alertes et recommandations.

En production : **<https://ener-vision.click>**

## Architecture

| Dossier | Service | Techno |
|---|---|---|
| `app/web` | Front | Angular |
| `services/core-api` | API REST (comptes, sites, mesures, alertes, recommandations, prévisions) | Spring Boot 4, Java 21 |
| `services/etl-worker` | Collecte des mesures et des alertes (cron) | Python |
| `services/prediction-service` | Entraînement quotidien, prévisions horaires, API de prédiction | Python, MLflow |
| `services/ml-service` | Exploration et campagnes d'entraînement hors ligne | Python, notebooks |
| `infra/db` | Schéma de la base (Liquibase) | PostgreSQL 16 + TimescaleDB |
| `infra/terraform`, `infra/deploy` | Infrastructure AWS et déploiement | Terraform, Docker Compose |
| `infra/proxy`, `infra/monitoring` | Reverse proxy et supervision | Caddy, Grafana, Prometheus, Loki |

Détail : [architecture applicative](docs/doc-technique/architecture-applicative.md).

## Lancer en local

Prérequis : Docker avec Compose, Node.js pour le front.

```bash
cp .env.example .env
```

Dans `.env`, renseigner au minimum :

- `JWT_SECRET` : `openssl rand -base64 32`
- `ADMIN_PASSWORD` : 12 caractères minimum (compte `ADMIN_EMAIL` créé au premier démarrage)
- `ENERGY_API_BASE_URL` et ses identifiants : l'API Mock de l'école
- `DATABASE_URL` et `SPRING_DATASOURCE_*` : mêmes identifiants que `POSTGRES_*`

Puis :

```bash
# base, migrations, core-api et collecte planifiée
docker compose up -d --build core-api scheduler

# front branché sur core-api, http://localhost:4200
cd app/web && npm install && npm run start:api
```

`npm start` lance le front seul, avec des données factices.

La partie ML (MLflow, entraînement, prévisions) est dans le profil `ml` :

```bash
docker compose --profile ml up -d mlflow prediction-service prediction-jobs
```

| Service local | Adresse |
|---|---|
| Front | http://localhost:4200 |
| core-api (Swagger) | http://localhost:8080/swagger-ui.html |
| PostgreSQL | `localhost:15432` |
| MLflow (profil `ml`) | http://localhost:5000 |

## Documentation

La documentation est disponible à cette adresse : https://enervision-project.github.io/smart-energy-optimizer/

La documentation complète est un site MkDocs (`docs/` et `docs/` de chaque service) :

```bash
uv sync
uv run mkdocs serve
```

Points d'entrée :

- [Documentation fonctionnelle](docs/doc-fonctionnelle/presentation.md)
- [Décisions d'architecture (ADR)](docs/doc-technique/decisions-architecture.md)
- [Modèle de données](docs/doc-technique/modele-de-donnees.md)
- [Gestion des comptes](docs/doc-technique/gestion-des-comptes.md)
- [Déploiement](docs/doc-technique/infra/deploiement.md) et [monitoring](docs/doc-technique/infra/monitoring.md)
