"""Configuration lue dans l'environnement (variables non préfixées, comme les autres services)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # répertoire contenant model.json (XGBoost) et model_meta.json
    model_dir: Path = Path("/models")
    log_level: str = "INFO"
    # Swagger / OpenAPI : désactivés en production
    enable_docs: bool = True
    host: str = "0.0.0.0"  # noqa: S104 - le conteneur n'est joignable que via le réseau Docker
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
