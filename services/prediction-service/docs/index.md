# Prediction Service

Service interne de prévision de consommation horaire. `prediction-service` sert le champion MLflow en mémoire ; `prediction-jobs` exécute l'entraînement quotidien et écrit chaque heure une série de prévisions dans PostgreSQL. Les deux conteneurs partagent le volume `/models`. MLflow utilise sa base PostgreSQL dédiée et les artefacts S3 déjà configurés.

## API

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| `POST` | `/predict` | Prévoit la consommation d'un site pour une heure à partir des features fournies. |
| `GET` | `/health` | Indique si un modèle est chargé et sa version. |

Le modèle de production HGB utilise `site_id`, `hour`, `day_of_week` (lundi = 0), `month` et `is_working_hours`. Les deux champs de lag restent optionnels pour la compatibilité avec les anciens modèles, mais le HGB de production les ignore. `temperature_celsius` est refusé par le contrat API.

```bash
curl -s http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{
  "site_id": "SITE001", "hour": 14, "day_of_week": 2, "month": 10,
  "is_working_hours": 1
}'
```

`/predict` renvoie `503` avant la première promotion d'un champion ; l'API reste démarrée. Un modèle déjà chargé continue de servir pendant les entraînements et les pannes MLflow. Le service cherche régulièrement la version `champion` du Registry et garde un cache versionné dans `/models/versions/`.

## Cycle quotidien

- À **01:00 Europe/Paris**, `prediction-jobs` déclenche un entraînement HGB. Au démarrage, il déclenche un rattrapage si le dernier entraînement réussi dans MLflow date strictement de plus de 25 heures.
- L'entraînement ne lit que les Parquet historiques (configuration `services/ml-service/configs/hgb_production.yaml`) : le modèle est ajusté sur `train.parquet`, puis évalué sur `validation.parquet` et `test.parquet`. Les mesures SQL ne servent pas encore à l'entraînement.
- Le challenger est comparé au champion sur **les mêmes lignes de `test.parquet`**. Il est promu si `test_macro_nmae_pct_challenger <= 0,96 × test_macro_nmae_pct_champion`, avec un score défini et positif pour le champion. Le premier candidat valide devient champion s'il n'existe pas encore de version.
- **Chaque heure à :05**, le job de prévisions utilise le champion disponible, même pendant un entraînement. Il calcule 24 heures successives en UTC à partir du prochain début d'heure et publie le lot complet dans `prediction_runs` et `predictions`. Les 24 heures à venir sont donc toujours couvertes ; pour chaque heure, `core-api` lit la série complète la plus récente.
- **Recalage de niveau** : avant publication, chaque prévision est multipliée par le ratio mesuré / prévu du site sur les 7 derniers jours (un ratio pour les heures travaillées, un pour les autres), car l'API Mock consomme 0,66 à 0,83 fois les niveaux du CSV d'entraînement. `predictions` garde la valeur publiée (`prediction_kwh`), la prévision brute du champion (`model_prediction_kwh`) et le ratio (`level_ratio`). Principe, garde-fous et résultats : section *Recalage de niveau* de la page « Fonctionnement du Prediction Service » ; code : `recalibration.py`.

L'historique des lots et des versions est conservé. `core-api` expose la série la plus récente avec `GET /api/v1/sites/{siteId}/predictions`, affichée par la page Prévisions du front.

## Préparation des données initiales

En local, `prediction-jobs` lit `.data/ml/splits` monté sous `/bootstrap`. En production, `TRAINING_BOOTSTRAP_URI` pointe vers `s3://<bucket-datalake>/ml/datasets/bootstrap/v1`. Le script `scripts/ml/upload-bootstrap.sh <bucket-datalake> v1` copie les trois Parquet, les relit et vérifie leur SHA-256. L'identité AWS du poste doit disposer d'un droit d'écriture sur ce préfixe ; le rôle EC2 ne reçoit que la lecture. Ce transfert est à faire une fois avant le premier entraînement en production.

## Paramètres

| Variable | Valeur habituelle | Usage |
| --- | --- | --- |
| `DATABASE_URL` | URL PostgreSQL de l'application | États des jobs, profils et prévisions ; les données SQL sont exclues de l'entraînement actuel. |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Tracking et Model Registry interne. |
| `REGISTERED_MODEL_NAME` | `enervision-hourly-consumption` | Nom stable dans le Registry. |
| `TRAINING_BOOTSTRAP_URI` | `/bootstrap` local, S3 en production | Source des Parquet historiques. |
| `TRAINING_TIMEZONE` | `Europe/Paris` | Heure de l'entraînement planifié (01:00). Les features calendaires sont toujours en UTC, comme le CSV d'entraînement et l'API Mock. |
| `VALIDATION_DAYS` | `14` | Paramètre réservé à une intégration future des données SQL ; ignoré dans le cycle historique actuel. |
| `MIN_CURRENT_VALIDATION_HOURS` | `168` | Paramètre réservé à une intégration future des données SQL ; ignoré dans le cycle historique actuel. |
| `MODEL_DIR` | `/models` | Cache local du champion. |
| `MODEL_REFRESH_SECONDS` | `60` | Vérification périodique de l'alias dans l'API. |
| `LEVEL_RECALIBRATION` | `true` | Recalage de niveau des prévisions publiées ; `false` publie la prévision brute du champion (ratio 1 enregistré). |

## Développement

```bash
docker compose --profile ml up -d db migrate mlflow prediction-service prediction-jobs
cd services/prediction-service
uv sync --extra dev
ruff check src tests
pytest -q
```

Les migrations Liquibase doivent réussir avant le démarrage de `prediction-jobs`. Consulter ses logs pour les erreurs d'accès S3/SQL, les runs MLflow et la publication des prévisions.
