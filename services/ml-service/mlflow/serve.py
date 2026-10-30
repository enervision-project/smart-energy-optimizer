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
            "--artifacts-destination", os.environ.get("MLFLOW_ARTIFACTS_DESTINATION", "/mlartifacts"),
            "--allowed-hosts", "localhost:*,127.0.0.1:*,mlflow,mlflow:5000",
        ],
    )
