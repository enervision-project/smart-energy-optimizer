"""Run the 96 weather-free HGB trials with Docker Compose: run_experiments.py [--dry-run] [--campaign-id ID --resume]"""

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
        # Created private; no secret is displayed.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(text.encode("utf-8"))
        print("Configuration locale créée depuis .env.example.", flush=True)
    elif text != original:
        path.write_bytes(text.encode("utf-8"))
        print("JWT_SECRET initialisé ; les autres paramètres .env sont conservés.", flush=True)
    return os.environ.get("MLFLOW_PORT") or env_value(text, "MLFLOW_PORT") or "5000"


def build_steps(root: Path, campaign: str, resume: bool = False) -> list[Step]:
    compose = (
        "docker", "compose", "--profile", "training",
        "-f", str(root / "compose.yaml"),
        "-f", str(root / "services/ml-service/compose.training.yaml"),
    )
    search = (
        *compose, "run", "--rm", "--no-deps", "--entrypoint", "python",
        "ml-trainer", "-m", "training.search_hgb",
        "--config", "configs/hgb_search_no_weather.yaml", "--campaign-id", campaign,
    )
    if resume:
        search = (*search, "--resume")
    return [
        Step("Construire l'image d'entraînement", (*compose, "build", "ml-trainer")),
        Step("Démarrer MLflow et attendre son état sain", (
            "docker", "compose", "--profile", "ml", "-f", str(root / "compose.yaml"),
            "up", "-d", "--build", "--wait", "--wait-timeout", "180", "mlflow",
        )),
        Step("HGB sans météo : 24 configurations pour chacune des 4 variantes de lags", search),
    ]


def check_inputs(root: Path) -> None:
    required = [
        root / "compose.yaml",
        root / "services/ml-service/compose.training.yaml",
        root / ".data/ml/splits/train.parquet",
        root / ".data/ml/splits/validation.parquet",
        root / "services/ml-service/configs/hgb_search_no_weather.yaml",
        root / "services/ml-service/configs/hist_gradient_boosting_no_weather.yaml",
    ]
    if not (root / ".env").is_file():
        required.append(root / ".env.example")
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Fichiers requis manquants :\n  " + "\n  ".join(missing)
            + "\nLes Parquet train et validation sont à récupérer séparément de Git ; "
            "ce lanceur ne les génère pas."
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
    # An empty shell variable must not hide the secret from the .env file.
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


def run_workflow(root: Path, campaign: str, dry_run: bool = False, resume: bool = False) -> None:
    steps = build_steps(root, campaign, resume)
    print(f"Projet : {root}\nCampagne : {campaign}", flush=True)
    print(
        "96 entraînements HGB sans météo : 24 configurations par variante de lags, "
        "sur les Parquet train et validation existants.",
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
    env = execution_environment(root)
    for index, step in enumerate(steps, 1):
        print(f"\n[{index}/{len(steps)}] {step.label}", flush=True)
        subprocess.run(step.command, cwd=root, env=env, check=True)
    print(f"\nTerminé. MLflow : http://localhost:{port}", flush=True)
    print("Expérience : consommation-horaire-sans-meteo-v1", flush=True)
    print(f"Filtrer les runs par le tag campaign_id : {campaign}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lancer les 96 essais HGB sans météo avec Docker.",
        epilog=(
            "Python standard uniquement, sans venv. Fournir les Parquet train et validation "
            "dans .data/ml/splits. Aucun Parquet n'est généré ou remplacé ; "
            "le jeu de test n'est ni requis ni utilisé."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Afficher le parcours sans aucun effet.")
    parser.add_argument(
        "--campaign-id", help="Identifiant unique de campagne MLflow ; généré automatiquement par défaut.",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Reprendre les essais d'un --campaign-id existant.",
    )
    args = parser.parse_args(argv)
    if args.resume and not args.campaign_id:
        parser.error("--resume nécessite --campaign-id pour identifier la campagne à reprendre.")
    campaign = args.campaign_id or (
        "hgb-no-weather-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9_-]+", campaign):
        parser.error("campaign-id doit contenir uniquement lettres, chiffres, tirets ou underscores.")
    root = Path(__file__).resolve().parents[2]
    try:
        run_workflow(root, campaign, dry_run=args.dry_run, resume=args.resume)
    except subprocess.CalledProcessError as error:
        print(f"\nArrêt : une commande a échoué (code {error.returncode}).", flush=True)
        return error.returncode
    except (OSError, ValueError, RuntimeError) as error:
        print(f"\nArrêt : {error}", flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu. Les runs déjà terminés restent dans MLflow.", flush=True)
        print(
            f"Reprendre : python3 services/ml-service/run_experiments.py --campaign-id {campaign} --resume",
            flush=True,
        )
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
