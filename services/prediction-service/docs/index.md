# Prediction Service

Service interne qui sert le modèle de prévision de consommation (XGBoost) en HTTP.
Il n'est pas exposé publiquement : joignable depuis les autres conteneurs (`http://prediction-service:8000`)
et, sur l'EC2, via `127.0.0.1:8000` (tunnel SSM).

## Endpoints

| Méthode | Chemin     | Rôle                                                   |
| ------- | ---------- | ------------------------------------------------------ |
| `POST`  | `/predict` | Prédit la consommation à partir d'une ligne de features |
| `GET`   | `/health`  | État du service et version du modèle chargé            |

### `POST /predict`

| Champ                 | Type        | Contrainte                    |
| --------------------- | ----------- | ----------------------------- |
| `site_id`             | texte       | `SITE\d{3,}`, connu du modèle |
| `hour`                | entier      | 0–23                          |
| `day_of_week`         | entier      | 0–6 (lundi = 0)               |
| `month`               | entier      | 1–12                          |
| `lag_24h`             | décimal     | ≥ 0, optionnel (manquant)     |
| `lag_168h`            | décimal     | ≥ 0, optionnel (manquant)     |
| `temperature_celsius` | décimal     | −60–60, optionnel (manquant)  |
| `is_working_hours`    | entier      | 0 ou 1                        |

```bash
curl -s http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{
  "site_id": "SITE001", "hour": 14, "day_of_week": 2, "month": 10,
  "lag_24h": 12.5, "lag_168h": 11.0, "temperature_celsius": 18.2, "is_working_hours": 1
}'
# {"prediction": 12.3, "model_version": "2026-10-23"}
```

Réponses : `200`, `422` (validation ou site inconnu), `503` (aucun modèle chargé).

## Artefacts du modèle

Le répertoire `MODEL_DIR` (`/models`, volume Docker `ml_models`) contient :

- `model.json` : booster XGBoost (`Booster.save_model`), colonnes dans l'ordre du tableau ci-dessus ;
- `model_meta.json` : `{"version": "...", "site_ids": ["SITE001", "SITE002"]}`. La position d'un site
  dans `site_ids` est la valeur numérique de `site_id` utilisée à l'entraînement.

## Configuration

| Variable      | Défaut    | Rôle                                  |
| ------------- | --------- | ------------------------------------- |
| `MODEL_DIR`   | `/models` | Répertoire des artefacts              |
| `LOG_LEVEL`   | `INFO`    |                                       |
| `ENABLE_DOCS` | `true`    | Swagger sur `/docs` (faux en prod)    |

## Développement

```bash
cd services/prediction-service
pip install -e '.[dev]'
ruff check . && ruff format --check .
pytest --cov=src
```
