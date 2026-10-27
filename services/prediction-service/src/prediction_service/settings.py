"""Configuration lue dans l'environnement (variables non préfixées, comme les autres services)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # répertoire contenant model.json (XGBoost) et model_meta.json
    model_dir: Path = Path("/models")
    database_url: str = ""
    mlflow_tracking_uri: str = ""
    registered_model_name: str = "enervision-hourly-consumption"
    training_experiment: str = "consommation-horaire-production"
    training_bootstrap_uri: str = ""
    training_config: Path = Path("/app/configs/hgb_production.yaml")
    # Réservés au futur cycle SQL ; le cycle actuel utilise les trois Parquet historiques.
    validation_days: int = 14
    min_current_validation_hours: int = 168
    training_timezone: str = "Europe/Paris"
    model_refresh_seconds: int = 60
    log_level: str = "INFO"
    # Swagger / OpenAPI : désactivés en production
    enable_docs: bool = True
    host: str = "0.0.0.0"  # noqa: S104 - le conteneur n'est joignable que via le réseau Docker
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
