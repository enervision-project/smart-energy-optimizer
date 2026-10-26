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
- Le dataset réunit `train.parquet` et `validation.parquet` historiques du préfixe S3 d'amorçage avec les nouvelles heures de `readings_hours` dès que chaque site historique dispose d'au moins 168 heures SQL valides. Avant ce seuil, l'entraînement utilise seulement l'historique. `test.parquet` reste réservé à l'évaluation hors ligne. Les 14 derniers jours disponibles forment la validation chronologique.
- Le challenger est comparé au champion sur **les mêmes lignes**. Il est promu si `val_macro_nmae_pct_challenger <= 0,96 × val_macro_nmae_pct_champion`, avec un score défini et positif pour le champion. Le premier candidat valide devient champion s'il n'existe pas encore de version.
- **Chaque heure à :05**, le job de prévisions utilise le champion disponible, même pendant un entraînement. Il calcule 24 heures successives en UTC à partir du prochain début d'heure et publie le lot complet dans `prediction_runs` et `predictions`. Les 24 heures à venir sont donc toujours couvertes ; pour chaque heure, `core-api` lit la série complète la plus récente.

L'historique des lots et des versions est conservé. La lecture par `core-api` et Angular fera l'objet d'une phase ultérieure.

## Préparation des données initiales

En local, `prediction-jobs` lit `.data/ml/splits` monté sous `/bootstrap`. En production, `TRAINING_BOOTSTRAP_URI` pointe vers `s3://<bucket-datalake>/ml/datasets/bootstrap/v1`. Le script `scripts/ml/upload-bootstrap.sh <bucket-datalake> v1` copie les trois Parquet, les relit et vérifie leur SHA-256. L'identité AWS du poste doit disposer d'un droit d'écriture sur ce préfixe ; le rôle EC2 ne reçoit que la lecture. Ce transfert est à faire une fois avant le premier entraînement en production.

## Paramètres

| Variable | Valeur habituelle | Usage |
| --- | --- | --- |
| `DATABASE_URL` | URL PostgreSQL de l'application | Lecture `readings_hours`/`site_profiles`, jobs et prévisions ; utilisée par `prediction-jobs`. |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Tracking et Model Registry interne. |
| `REGISTERED_MODEL_NAME` | `enervision-hourly-consumption` | Nom stable dans le Registry. |
| `TRAINING_BOOTSTRAP_URI` | `/bootstrap` local, S3 en production | Source des Parquet historiques. |
| `TRAINING_TIMEZONE` | `Europe/Paris` | Heure des jobs et features calendaires. |
| `VALIDATION_DAYS` | `14` | Fenêtre de validation chronologique. |
| `MIN_CURRENT_VALIDATION_HOURS` | `168` | Heures SQL minimales par site avant de les intégrer au snapshot d'entraînement. |
| `MODEL_DIR` | `/models` | Cache local du champion. |
| `MODEL_REFRESH_SECONDS` | `60` | Vérification périodique de l'alias dans l'API. |

## Développement

```bash
docker compose --profile ml up -d db migrate mlflow prediction-service prediction-jobs
cd services/prediction-service
uv sync --extra dev
ruff check src tests
pytest -q
```

Les migrations Liquibase doivent réussir avant le démarrage de `prediction-jobs`. Consulter ses logs pour les erreurs d'accès S3/SQL, les runs MLflow et la publication des prévisions.
