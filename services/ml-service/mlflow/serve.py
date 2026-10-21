"""Demarre le serveur local avec les fichiers servis depuis le volume persistant."""

import os

from settings import backend_uri


if __name__ == "__main__":
    os.execvp(
        "mlflow",
        [
            "mlflow", "server",
            "--host", "0.0.0.0",
            "--port", "5000",
            "--workers", "1",
            "--backend-store-uri", backend_uri(),
            "--serve-artifacts",
            "--artifacts-destination", "/mlartifacts",
            "--allowed-hosts", "localhost:*,127.0.0.1:*,mlflow,mlflow:5000",
        ],
    )
