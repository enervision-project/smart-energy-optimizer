"""Configuration de la base dediee a MLflow."""

import os

from sqlalchemy.engine import URL


def database_settings() -> dict:
    required = ("MLFLOW_DB_NAME", "MLFLOW_DB_USER", "MLFLOW_DB_PASSWORD")
    for key in required:
        if not os.environ.get(key):
            raise ValueError(f"Renseigner {key}.")

    return {
        "host": os.environ.get("MLFLOW_DB_HOST", "db"),
        "port": int(os.environ.get("MLFLOW_DB_PORT", "5432")),
        "dbname": os.environ["MLFLOW_DB_NAME"],
        "user": os.environ["MLFLOW_DB_USER"],
        "password": os.environ["MLFLOW_DB_PASSWORD"],
    }


def backend_uri() -> str:
    settings = database_settings()
    return URL.create(
        "postgresql+psycopg2",
        username=settings["user"],
        password=settings["password"],
        host=settings["host"],
        port=settings["port"],
        database=settings["dbname"],
    ).render_as_string(hide_password=False)
