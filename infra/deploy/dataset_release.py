"""Préparer et publier un snapshot immuable des Parquet choisis par DVC.

prepare s'exécute dans l'image DVC après pull. publish et verify utilisent
uniquement Python standard et AWS CLI ; aucun entraînement n'est lancé.
"""
from __future__ import annotations

import argparse
from hashlib import md5, sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

NAMES = ("train.parquet", "validation.parquet", "test.parquet")
PREFIX = "ml/datasets/bootstrap"


def fingerprints(path: Path) -> dict:
    sha, digest = sha256(), md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
            digest.update(block)
            size += len(block)
    return {"sha256": sha.hexdigest(), "md5": digest.hexdigest(), "size": size}


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def validate_release(value: dict, revision: str | None = None) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Version de manifeste inconnue.")
    version = value.get("dataset_id", "")
    bucket = value.get("bucket", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", version):
        raise ValueError("Identifiant de dataset invalide.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Bucket invalide.")
    expected = f"s3://{bucket}/{PREFIX}/{version}"
    if value.get("dataset_uri") != expected:
        raise ValueError("URI du snapshot incohérente.")
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("git_revision", "")):
        raise ValueError("Commit Git invalide.")
    if revision is not None and value["git_revision"] != revision:
        raise ValueError("Le manifeste ne correspond pas au commit déployé.")
    files = value.get("files", {})
    if set(files) != set(NAMES):
        raise ValueError("Le manifeste doit contenir exactement les trois Parquet.")
    for name, info in files.items():
        if not re.fullmatch(r"[0-9a-f]{64}", info.get("sha256", "")):
            raise ValueError(f"{name}: empreinte SHA-256 invalide.")
        if not isinstance(info.get("size"), int) or info["size"] <= 0:
            raise ValueError(f"{name}: taille invalide.")
    return value


def dataset_manifest(release: dict) -> dict:
    # Le commit appartient à la release, pas au snapshot partagé par plusieurs releases.
    return {key: release[key] for key in ("schema_version", "dataset_id", "files")}


def prepare(root: Path, revision: str) -> dict:
    # Dépendances déjà présentes dans l'image Docker DVC.
    import yaml
    from dvc.repo import Repo

    pointer = root / "ml-datasets.dvc"
    data = yaml.safe_load(pointer.read_text())
    with Repo(str(root)) as repo:
        remote = repo.config["remote"][repo.config["core"]["remote"]]["url"]
        if repo.status(targets=[str(pointer)]):
            raise ValueError("Les fichiers locaux diffèrent de la référence DVC.")
    return prepare_from_metadata(root, revision, data, remote)


def prepare_from_metadata(root: Path, revision: str, data: dict, remote: str) -> dict:
    if not isinstance(data, dict) or len(data.get("outs", [])) != 1:
        raise ValueError("Une seule sortie DVC est attendue.")
    output = data["outs"][0]
    version = output.get("md5", "")
    if not re.fullmatch(r"[0-9a-f]{32}\.dir", version):
        raise ValueError("Le dataset doit être un répertoire DVC versionné par MD5.")
    if output.get("path") != ".data/ml/splits" or output.get("nfiles") != 3:
        raise ValueError("La référence DVC doit couvrir les trois Parquet de splits.")
    url = urlparse(remote)
    if url.scheme != "s3" or url.path.rstrip("/") != "/ml/datasets/dvc":
        raise ValueError("Le remote DVC doit utiliser le préfixe S3 ml/datasets/dvc.")
    tree = root / ".dvc/cache/files/md5" / version[:2] / version[2:]
    content = tree.read_bytes()
    if md5(content, usedforsecurity=False).hexdigest() + ".dir" != version:
        raise ValueError("Manifeste du cache DVC corrompu.")
    entries = json.loads(content)
    expected = {entry["relpath"]: entry["md5"] for entry in entries}
    if len(entries) != 3 or set(expected) != set(NAMES):
        raise ValueError("Le cache DVC doit référencer exactement les trois Parquet.")
    folder = root / ".data/ml/splits"
    if {p.name for p in folder.iterdir()} != set(NAMES):
        raise ValueError("Le dossier splits contient des fichiers inattendus.")
    files = {}
    for name in NAMES:
        info = fingerprints(folder / name)
        if info["md5"] != expected[name]:
            raise ValueError(f"{name}: contenu différent de la version DVC.")
        files[name] = {key: info[key] for key in ("sha256", "size")}
    if sum(info["size"] for info in files.values()) != output.get("size"):
        raise ValueError("La taille totale diffère de la référence DVC.")
    return validate_release({
        "schema_version": 1, "dataset_id": version, "bucket": url.netloc,
        "dataset_uri": f"s3://{url.netloc}/{PREFIX}/{version}",
        "git_revision": revision, "files": files,
    }, revision)


class S3:
    def __init__(self, bucket: str):
        self.bucket = bucket

    def _call(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["aws", "s3api", *args, "--bucket", self.bucket, "--output", "json", "--no-cli-pager"],
            text=True, capture_output=True,
        )

    def download(self, key: str, target: Path) -> bool:
        result = self._call(["get-object", "--key", key, str(target)])
        if result.returncode:
            if any(code in result.stderr for code in ["(NoSuchKey)", "(404)", "(NotFound)"]):
                return False
            if any(code in result.stderr for code in ["(AccessDenied)", "(403)"]):
                # Avec ListBucket limité par s3:prefix, GET peut masquer une absence par 403.
                # Seule une liste autorisée du préfixe exact peut confirmer cette absence.
                listing = self._call([
                    "list-objects-v2", "--prefix", key, "--max-keys", "1", "--no-paginate",
                ])
                if listing.returncode == 0:
                    objects = json.loads(listing.stdout).get("Contents", [])
                    if not any(item.get("Key") == key for item in objects):
                        return False
            raise RuntimeError(f"Lecture S3 impossible pour {key}: {result.stderr.strip()}")
        return True

    def upload_if_absent(self, key: str, source: Path) -> None:
        # Pas d'écrasement, même si deux publications arrivent simultanément.
        result = self._call([
            "put-object", "--key", key, "--body", str(source), "--if-none-match", "*",
        ])
        if result.returncode and not any(
            code in result.stderr for code in ["(PreconditionFailed)", "(ConditionalRequestConflict)"]
        ):
            raise RuntimeError(f"Écriture S3 impossible pour {key}: {result.stderr.strip()}")


def ensure_object(store, key: str, source: Path, temporary: Path) -> None:
    expected = fingerprints(source)
    downloaded = temporary / "download"
    if not store.download(key, downloaded):
        store.upload_if_absent(key, source)
        if not store.download(key, downloaded):
            raise RuntimeError(f"Objet S3 introuvable après publication : {key}")
    if fingerprints(downloaded) != expected:
        raise ValueError(f"Objet S3 existant différent, aucun écrasement : {key}")


def publish(root: Path, release: dict, store=None) -> None:
    release = validate_release(release)
    folder = root / ".data/ml/splits"
    # Vérifier les trois sources avant la première écriture distante.
    for name in NAMES:
        actual = fingerprints(folder / name)
        if {k: actual[k] for k in ("sha256", "size")} != release["files"][name]:
            raise ValueError(f"{name}: fichier local différent du manifeste.")
    store = store or S3(release["bucket"])
    prefix = f"{PREFIX}/{release['dataset_id']}"
    with TemporaryDirectory(prefix="dataset-publish-") as tmp:
        temporary = Path(tmp)
        for name in NAMES:
            ensure_object(store, f"{prefix}/{name}", folder / name, temporary)
        checksums = temporary / "sha256.txt"
        checksums.write_text("".join(
            f"{release['files'][name]['sha256']}  {name}\n" for name in NAMES
        ))
        ensure_object(store, f"{prefix}/sha256.txt", checksums, temporary)
        # Marqueur de complétude publié seulement après vérification des trois objets.
        manifest = temporary / "manifest.json"
        manifest.write_bytes(json_bytes(dataset_manifest(release)))
        ensure_object(store, f"{prefix}/manifest.json", manifest, temporary)


def verify_remote(release: dict, store=None) -> None:
    release = validate_release(release)
    store = store or S3(release["bucket"])
    prefix = f"{PREFIX}/{release['dataset_id']}"
    with TemporaryDirectory(prefix="dataset-verify-") as tmp:
        temporary = Path(tmp)
        target = temporary / "manifest.json"
        if not store.download(f"{prefix}/manifest.json", target):
            raise ValueError("Snapshot incomplet : manifeste de publication absent.")
        if json.loads(target.read_text()) != dataset_manifest(release):
            raise ValueError("Le manifeste S3 ne correspond pas à la release.")
        for name in NAMES:
            if not store.download(f"{prefix}/{name}", target):
                raise ValueError(f"Snapshot incomplet : {name} absent.")
            actual = fingerprints(target)
            if {k: actual[k] for k in ("sha256", "size")} != release["files"][name]:
                raise ValueError(f"{name}: empreinte distante différente.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "publish", "verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--release", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--git-revision")
    parser.add_argument("--bucket")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--remote", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if not args.output or not args.git_revision:
                parser.error("prepare nécessite --output et --git-revision")
            release = prepare(args.root, args.git_revision)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(json_bytes(release))
        else:
            if args.release:
                release = validate_release(json.loads(args.release.read_text()), args.git_revision)
            elif args.command == "publish" and args.bucket:
                # Compatibilité avec la commande manuelle upload-bootstrap.sh <bucket> [version].
                files = {}
                for name in NAMES:
                    info = fingerprints(args.root / ".data/ml/splits" / name)
                    files[name] = {k: info[k] for k in ("sha256", "size")}
                revision = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=args.root, capture_output=True,
                    text=True, check=True,
                ).stdout.strip()
                release = validate_release({
                    "schema_version": 1, "dataset_id": args.version, "bucket": args.bucket,
                    "dataset_uri": f"s3://{args.bucket}/{PREFIX}/{args.version}",
                    "git_revision": revision, "files": files,
                })
            else:
                parser.error("--release requis, ou --bucket pour une publication manuelle")
            if args.command == "publish":
                publish(args.root, release)
            elif args.remote:
                verify_remote(release)
        print(release["dataset_uri"], flush=True)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Dataset refusé : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
