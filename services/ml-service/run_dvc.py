"""Versionner ou récupérer les trois Parquet existants avec DVC dans Docker.

Depuis la racine, sous Linux/WSL (Python standard, sans venv) :
    python3 services/ml-service/run_dvc.py status
    python3 services/ml-service/run_dvc.py pull --profile enervision
    python3 services/ml-service/run_dvc.py add
    python3 services/ml-service/run_dvc.py push --profile enervision
    python3 services/ml-service/run_dvc.py pull --dry-run

Après un changement volontaire des données : add, push, puis commit Git du
fichier ml-datasets.dvc. Pour récupérer une version : git checkout, puis pull.
Les commandes add/push/pull portent ensemble sur train, validation et test ;
aucun entraînement ni préparation des données n'est lancé.

Les identifiants restent sur le poste. Avec AWS SSO, se connecter d'abord sur
l'hôte : aws sso login --profile enervision. Le dossier ~/.aws est monté en
lecture seule ; le conteneur ne peut pas renouveler cette session à ta place.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess


IMAGE = "enervision-dvc:local"
DATASET = ".data/ml/splits"
POINTER = "ml-datasets.dvc"
PARQUETS = {"train.parquet", "validation.parquet", "test.parquet"}
AWS_ENV = (
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_REGION", "AWS_DEFAULT_REGION",
)


def dvc_arguments(command: str) -> list[str]:
    if command == "add":
        # Le cache est alimenté sans remplacer ni relier les fichiers originaux.
        return ["add", "--no-relink", DATASET]
    if command == "version":
        return ["version"]
    if command in {"push", "pull", "status"}:
        return [command, POINTER]
    raise ValueError("Commande DVC non prise en charge : " + command)


def check_inputs(root: Path, command: str) -> None:
    required = [
        "services/ml-service/Dockerfile.dvc-tools",
        "services/ml-service/requirements-dvc.txt",
        "services/ml-service/requirements-dvc.lock",
        "services/ml-service/requirements-dvc-build.lock",
        ".dvc/config",
    ]
    if command != "version":
        required.append(POINTER)
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError("Fichiers requis manquants : " + ", ".join(missing))
    if command == "add":
        folder = root / DATASET
        present = {path.name for path in folder.iterdir()} if folder.is_dir() else set()
        if present != PARQUETS or not all((folder / name).is_file() for name in PARQUETS):
            raise ValueError(
                DATASET + " doit contenir exactement train.parquet, validation.parquet "
                "et test.parquet. Récupérer les données avant de lancer add."
            )


def docker_commands(root: Path, command: str, aws_dir: Path, env: dict[str, str]) -> list[list[str]]:
    context = root / "services/ml-service"
    build = [
        "docker", "build", "--quiet", "--tag", IMAGE,
        "--build-arg", f"DVC_UID={os.getuid()}",
        "--build-arg", f"DVC_GID={os.getgid()}",
        "--file", str(context / "Dockerfile.dvc-tools"), str(context),
    ]
    run = [
        "docker", "run", "--rm",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--workdir", "/workspace",
        "--env", "HOME=/tmp",
        "--env", "DVC_NO_ANALYTICS=1",
        "--mount", f"type=bind,source={root},target=/workspace",
    ]
    if command in {"push", "pull"}:
        if aws_dir.is_dir():
            run += ["--mount", f"type=bind,source={aws_dir},target=/tmp/.aws,readonly"]
        # Passer les noms, jamais les valeurs des secrets dans les arguments.
        for name in (*AWS_ENV, "AWS_PROFILE"):
            if env.get(name):
                run += ["--env", name]
    run += [IMAGE, *dvc_arguments(command)]
    return [build, run]


def run_workflow(
    root: Path, command: str, profile: str | None = None,
    aws_dir: Path | None = None, dry_run: bool = False,
) -> None:
    if not hasattr(os, "getuid"):
        raise RuntimeError("Exécuter ce lanceur dans Linux ou WSL.")
    env = os.environ.copy()
    profile = profile or env.get("AWS_PROFILE") or env.get("AWS_DEFAULT_PROFILE")
    if profile:
        env["AWS_PROFILE"] = profile
    aws_dir = (aws_dir or Path.home() / ".aws").expanduser().resolve()
    commands = docker_commands(root, command, aws_dir, env)
    if dry_run:
        print("Simulation : aucune écriture et aucune commande exécutée.", flush=True)
        for args in commands:
            print(shlex.join(args), flush=True)
        return
    check_inputs(root, command)
    if not shutil.which("docker"):
        raise RuntimeError("Docker doit être installé et démarré.")
    if command in {"push", "pull"} and not (
        aws_dir.is_dir()
        or (env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"))
    ):
        raise RuntimeError(
            "Configurer un profil AWS dans ~/.aws ou fournir des identifiants temporaires "
            "par variables d'environnement. Aucun identifiant n'est stocké dans Git."
        )
    for args in commands:
        print(shlex.join(args), flush=True)
        subprocess.run(args, cwd=root, env=env, check=True)
    if command == "add":
        print("Version locale enregistrée. Envoyer avec push avant de publier le fichier .dvc dans Git.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gérer les trois Parquet avec DVC dans Docker.")
    parser.add_argument("command", choices=["add", "push", "pull", "status", "version"])
    parser.add_argument("--profile", help="Profil AWS local ; AWS_PROFILE est utilisé par défaut.")
    parser.add_argument("--aws-dir", type=Path, help="Dossier AWS local à monter en lecture seule.")
    parser.add_argument("--dry-run", action="store_true", help="Afficher les commandes sans effet.")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        run_workflow(root, args.command, args.profile, args.aws_dir, args.dry_run)
    except subprocess.CalledProcessError as error:
        print(f"Arrêt : une commande a échoué (code {error.returncode}).", flush=True)
        return error.returncode
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Arrêt : {error}", flush=True)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
