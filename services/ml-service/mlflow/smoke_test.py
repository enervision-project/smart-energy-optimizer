import os
from pathlib import Path
from tempfile import TemporaryDirectory

from mlflow import MlflowClient


def main() -> None:
    client = MlflowClient(
        tracking_uri=os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    )
    name = "mlflow-setup-check"
    experiment = client.get_experiment_by_name(name)
    experiment_id = experiment.experiment_id if experiment else client.create_experiment(name)
    run_id = client.create_run(
        experiment_id, tags={"purpose": "verification-installation"}
    ).info.run_id

    try:
        client.log_param(run_id, "check", "tracking-and-artifacts")
        client.log_metric(run_id, "setup_ok", 1)
        with TemporaryDirectory() as directory, TemporaryDirectory() as downloads:
            path = Path(directory) / "verification.txt"
            expected = "MLflow : stockage des artefacts operationnel.\n"
            path.write_text(expected, encoding="utf-8")
            client.log_artifact(run_id, str(path))
            restored = Path(client.download_artifacts(run_id, path.name, downloads))
            if restored.read_text(encoding="utf-8") != expected:
                raise RuntimeError("Le fichier relu ne correspond pas au fichier envoye.")
        client.set_terminated(run_id, status="FINISHED")
    except Exception:
        client.set_terminated(run_id, status="FAILED")
        raise

    print(f"Verification MLflow reussie. Run : {run_id}")


if __name__ == "__main__":
    main()
