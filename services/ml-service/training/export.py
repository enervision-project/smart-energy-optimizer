"""Export an MLflow run: python -m training.export --run-id <id> --out-dir /export --version 2026-10-23"""

import argparse
import json
import os
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn

MODEL_FILE = "model.joblib"
META_FILE = "model_meta.json"


def export(run_id: str, out_dir: Path, version: str) -> dict:
    run = mlflow.get_run(run_id)
    features = run.data.params["features"].split(",")
    pipeline = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
    sites = pipeline.named_steps["preprocessing"].named_transformers_["site"].categories_[0]
    meta = {
        "version": version, "format": "sklearn", "features": features,
        "site_ids": [str(site) for site in sites], "mlflow_run_id": run_id,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_dir / MODEL_FILE)
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporter un pipeline sklearn pour le prediction-service.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI"))
    args = parser.parse_args()
    mlflow.set_tracking_uri(args.tracking_uri)
    print(json.dumps(export(args.run_id, args.out_dir, args.version), ensure_ascii=False))


if __name__ == "__main__":
    main()
