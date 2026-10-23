"""Tout lancer sous Linux/WSL, avec Python standard et Docker Compose.

Depuis la racine :
    python3 services/ml-service/run_experiments.py
    python3 services/ml-service/run_experiments.py --dry-run

Déposer d'abord le CSV combiné et les métadonnées dans .data/ml/raw.
Un lancement complet régénère les trois Parquet et exécute toutes les campagnes
Python existantes (59 entraînements avec les configurations actuelles).
Les entraînements utilisent uniquement train et validation.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import uuid


@dataclass(frozen=True)
class Step:
    label: str
    command: tuple[str, ...]


def env_value(text: str, key: str) -> str:
    match = re.search(
        rf"(?m)^[ \t]*(?:export[ \t]+)?{re.escape(key)}[ \t]*=[ \t]*([^\r\n]*)",
        text,
    )
    if not match:
        return ""
    value = match.group(1).strip()
    if not value or value.startswith("#"):
        return ""
    quoted = re.fullmatch(r"""(['"])(.*?)\1[ \t]*(?:#.*)?""", value)
    if quoted:
        return quoted.group(2)
    return re.split(r"[ \t]+#", value, maxsplit=1)[0].rstrip()


def ensure_local_env(root: Path) -> str:
    path = root / ".env"
    existed = path.is_file()
    original = (path if existed else root / ".env.example").read_bytes().decode("utf-8")
    text = original
    missing = [
        key for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
        if not os.environ.get(key, env_value(text, key))
    ]
    if missing:
        raise ValueError("Renseigner dans .env : " + ", ".join(missing))
    if not env_value(text, "JWT_SECRET"):
        jwt = os.environ.get("JWT_SECRET") or base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        pattern = r"(?m)^[ \t]*(?:export[ \t]+)?JWT_SECRET[ \t]*=[^\r\n]*"
        if re.search(pattern, text):
            text = re.sub(pattern, lambda _: "JWT_SECRET=" + jwt, text)
        else:
            newline = "\r\n" if "\r\n" in text else "\n"
            text += ("" if text.endswith("\n") else newline) + "JWT_SECRET=" + jwt + newline
    if not existed:
        # Création privée ; aucun secret n'est affiché.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(text.encode("utf-8"))
        print("Configuration locale créée depuis .env.example.", flush=True)
    elif text != original:
        path.write_bytes(text.encode("utf-8"))
        print("JWT_SECRET initialisé ; les autres paramètres .env sont conservés.", flush=True)
    return os.environ.get("MLFLOW_PORT") or env_value(text, "MLFLOW_PORT") or "5000"


def build_steps(root: Path, campaign: str, host_user: str) -> list[Step]:
    compose = (
        "docker", "compose", "--profile", "training", "--profile", "preparation",
        "-f", str(root / "compose.yaml"),
        "-f", str(root / "services/ml-service/compose.training.yaml"),
    )
    single = (*compose, "run", "--rm", "--no-deps", "ml-trainer")
    search = (
        *compose, "run", "--rm", "--no-deps", "--entrypoint", "python",
        "ml-trainer", "-m", "training.search_hgb",
    )
    reference_campaign = campaign + "-references"
    return [
        Step("Construire l'image de préparation et d'entraînement", (*compose, "build", "ml-trainer")),
        Step("Générer les trois Parquet", (
            *compose, "run", "--rm", "--no-deps", "--user", host_user, "ml-prepare",
        )),
        Step("Démarrer MLflow et attendre son état sain", (
            "docker", "compose", "--profile", "ml", "-f", str(root / "compose.yaml"),
            "up", "-d", "--build", "--wait", "--wait-timeout", "180", "mlflow",
        )),
        Step("Ridge avec les huit features", (
            *single, "--config", "configs/ridge.yaml", "--campaign-id", reference_campaign,
        )),
        Step("HGB avec les huit features", (
            *single, "--config", "configs/hist_gradient_boosting.yaml",
            "--campaign-id", reference_campaign,
        )),
        Step("HGB avec lags : huit ablations et vingt-quatre configurations", (
            *search, "--config", "configs/hgb_search.yaml",
            "--campaign-id", campaign + "-with-lags",
        )),
        Step("HGB de référence sans les deux lags", (
            *single, "--config", "configs/hgb_without_lags.yaml",
            "--campaign-id", reference_campaign,
        )),
        Step("HGB sans lags : vingt-quatre configurations", (
            *search, "--config", "configs/hgb_search_without_lags.yaml",
            "--campaign-id", campaign + "-without-lags",
        )),
    ]


def check_inputs(root: Path) -> None:
    required = [
        root / "compose.yaml",
        root / "services/ml-service/compose.training.yaml",
        root / ".data/ml/raw/all_sites_combined.csv",
        *(
            root / "services/ml-service/configs" / name
            for name in (
                "ridge.yaml", "hist_gradient_boosting.yaml", "hgb_without_lags.yaml",
                "hgb_search.yaml", "hgb_search_without_lags.yaml",
            )
        ),
    ]
    if not (root / ".env").is_file():
        required.append(root / ".env.example")
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    metadata = root / ".data/ml/raw/metadata"
    if not metadata.is_dir() or not any(metadata.glob("*_metadata.json")):
        missing.append(".data/ml/raw/metadata/*_metadata.json")
    if missing:
        raise FileNotFoundError(
            "Fichiers requis manquants :\n  " + "\n  ".join(missing)
            + "\nLe CSV et les métadonnées sont à récupérer séparément de Git."
        )


def check_docker(root: Path) -> None:
    if not shutil.which("docker"):
        raise RuntimeError("Installer Docker avec Docker Compose, puis relancer le script.")
    for command in [
        ["docker", "compose", "version"],
        ["docker", "info", "--format", "{{.ServerVersion}}"],
    ]:
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        if result.returncode:
            reason = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError("Docker/Compose indisponible : " + reason)


def execution_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Une variable vide du shell ne doit pas masquer le secret du fichier .env.
    if not env.get("JWT_SECRET"):
        env.pop("JWT_SECRET", None)
    env["TRAINING_GIT_REVISION"] = "unknown"
    env["TRAINING_GIT_DIRTY"] = "unknown"
    if shutil.which("git"):
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True,
        )
        if revision.returncode == 0:
            env["TRAINING_GIT_REVISION"] = revision.stdout.strip()
        if status.returncode == 0:
            env["TRAINING_GIT_DIRTY"] = "true" if status.stdout.strip() else "false"
    return env


def run_workflow(root: Path, campaign: str, dry_run: bool = False) -> None:
    host_user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "UID:GID"
    steps = build_steps(root, campaign, host_user)
    print(f"Projet : {root}\nCampagne : {campaign}", flush=True)
    print(
        "Parcours complet : préparation des Parquet puis 59 entraînements "
        "sur train et validation avec les configurations actuelles.",
        flush=True,
    )
    if dry_run:
        print("Simulation : aucune écriture et aucune commande exécutée.", flush=True)
        print("Le .env sera créé si nécessaire ; un JWT_SECRET manquant sera initialisé.", flush=True)
        for index, step in enumerate(steps, 1):
            print(f"\n[{index}/{len(steps)}] {step.label}\n{shlex.join(step.command)}", flush=True)
        return
    if not hasattr(os, "getuid"):
        raise RuntimeError("Exécuter ce script dans Linux ou WSL.")
    check_inputs(root)
    check_docker(root)
    port = ensure_local_env(root)
    (root / ".data/ml/splits").mkdir(parents=True, exist_ok=True)
    env = execution_environment(root)
    for index, step in enumerate(steps, 1):
        print(f"\n[{index}/{len(steps)}] {step.label}", flush=True)
        subprocess.run(step.command, cwd=root, env=env, check=True)
    print(f"\nTerminé. MLflow : http://localhost:{port}", flush=True)
    print("Expérience : consommation-horaire-parquet-v2", flush=True)
    print(
        "Filtrer les runs par le tag campaign_id :\n"
        f"  {campaign}-references\n  {campaign}-with-lags\n  {campaign}-without-lags",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Préparer les données et lancer toutes les campagnes ML avec Docker.",
        epilog=(
            "Python standard uniquement, sans venv. Déposer le CSV et les métadonnées "
            "dans .data/ml/raw avant le lancement. Les sorties Parquet existantes sont "
            "remplacées ; le test est préparé puis réservé à l'évaluation finale."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Afficher le parcours sans aucun effet.")
    parser.add_argument(
        "--campaign-id", help="Préfixe unique des campagnes MLflow ; généré automatiquement par défaut.",
    )
    args = parser.parse_args(argv)
    campaign = args.campaign_id or (
        "offline-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9_-]+", campaign):
        parser.error("campaign-id doit contenir uniquement lettres, chiffres, tirets ou underscores.")
    root = Path(__file__).resolve().parents[2]
    try:
        run_workflow(root, campaign, args.dry_run)
    except subprocess.CalledProcessError as error:
        print(f"\nArrêt : une commande a échoué (code {error.returncode}).", flush=True)
        return error.returncode
    except (OSError, ValueError, RuntimeError) as error:
        print(f"\nArrêt : {error}", flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu. Les runs déjà terminés restent dans MLflow.", flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
