from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # directory holding model.json (XGBoost) and model_meta.json
    model_dir: Path = Path("/models")
    database_url: str = ""
    mlflow_tracking_uri: str = ""
    registered_model_name: str = "enervision-hourly-consumption"
    training_experiment: str = "consommation-horaire-production"
    training_bootstrap_uri: str = ""
    training_config: Path = Path("/app/configs/hgb_production.yaml")
    # Training schedule (01:00); calendar features are in UTC.
    training_timezone: str = "Europe/Paris"
    model_refresh_seconds: int = 60
    # Forecast level recalibration; false publishes the raw champion forecast.
    level_recalibration: bool = True
    log_level: str = "INFO"
    # Swagger / OpenAPI: disabled in production
    enable_docs: bool = True
    host: str = "0.0.0.0"  # noqa: S104 - the container is only reachable through the Docker network
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
