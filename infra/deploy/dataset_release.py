"""Prepare and publish an immutable snapshot of the Parquet files selected by DVC."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_RELEASE = ".data/ml/dataset-release.json"
DEPLOY_RELEASE = "dataset-release.json"


def project_path(root: Path, relative: str) -> Path:
    """Build an internal path, without traversal or symlinks."""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("Chemin hors du projet interdit.")
    current = root.resolve()
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Lien symbolique interdit pour les fichiers du dataset.")
    return current


def selected_path(root: Path, value: Path, allowed: tuple[str, ...]) -> Path:
    """Return a path built by the program, not the one given on the CLI."""
    requested = Path(value)
    if ".." in requested.parts:
        raise ValueError("Traversée de répertoire interdite.")
    if not requested.is_absolute():
        requested = root / requested
    for relative in allowed:
        expected = project_path(root, relative)
        if requested == expected:
            return expected
    raise ValueError("Emplacement autorisé : " + ", ".join(allowed))


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


def checked_text(value, pattern: str, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(message)
    match = re.fullmatch(pattern, value)
    if match is None:
        raise ValueError(message)
    return match.group(0)


def validate_release(value: dict, revision: str | None = None) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Version de manifeste inconnue.")
    version = checked_text(
        value.get("dataset_id"), r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
        "Identifiant de dataset invalide.",
    )
    bucket = checked_text(
        value.get("bucket"), r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", "Bucket invalide.",
    )
    expected = f"s3://{bucket}/{PREFIX}/{version}"
    if value.get("dataset_uri") != expected:
        raise ValueError("URI du snapshot incohérente.")
    git_revision = checked_text(value.get("git_revision"), r"[0-9a-f]{40}", "Commit Git invalide.")
    if revision is not None and git_revision != revision:
        raise ValueError("Le manifeste ne correspond pas au commit déployé.")
    original = value.get("files")
    if not isinstance(original, dict) or set(original) != set(NAMES):
        raise ValueError("Le manifeste doit contenir exactement les trois Parquet.")
    files = {}
    for name in NAMES:
        info = original[name]
        if not isinstance(info, dict):
            raise ValueError(f"{name}: métadonnées invalides.")
        digest = checked_text(info.get("sha256"), r"[0-9a-f]{64}", f"{name}: SHA-256 invalide.")
        size = info.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError(f"{name}: taille invalide.")
        files[name] = {"sha256": digest, "size": size}
    # Rebuild only the allowed data: no extra key propagates.
    return {
        "schema_version": 1, "dataset_id": version, "bucket": bucket,
        "dataset_uri": expected, "git_revision": git_revision, "files": files,
    }


def dataset_manifest(release: dict) -> dict:
    # The commit belongs to the release, not to the snapshot shared by several releases.
    return {key: release[key] for key in ("schema_version", "dataset_id", "files")}


def prepare(root: Path, revision: str) -> dict:
    # Dependencies already in the DVC Docker image.
    import yaml
    from dvc.repo import Repo

    pointer = project_path(root, "ml-datasets.dvc")
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
    tree = project_path(root, f".dvc/cache/files/md5/{version[:2]}/{version[2:]}")
    content = tree.read_bytes()
    if md5(content, usedforsecurity=False).hexdigest() + ".dir" != version:
        raise ValueError("Manifeste du cache DVC corrompu.")
    entries = json.loads(content)
    expected = {entry["relpath"]: entry["md5"] for entry in entries}
    if len(entries) != 3 or set(expected) != set(NAMES):
        raise ValueError("Le cache DVC doit référencer exactement les trois Parquet.")
    folder = project_path(root, ".data/ml/splits")
    if {p.name for p in folder.iterdir()} != set(NAMES):
        raise ValueError("Le dossier splits contient des fichiers inattendus.")
    files = {}
    for name in NAMES:
        info = fingerprints(project_path(root, f".data/ml/splits/{name}"))
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


def checked_key(key: str) -> str:
    filename = r"(?:train[.]parquet|validation[.]parquet|test[.]parquet|sha256[.]txt|manifest[.]json)"
    return checked_text(
        key, rf"{PREFIX}/[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}/{filename}",
        "Clé S3 hors du préfixe dataset ou fichier non autorisé.",
    )


@contextmanager
def aws_parameter_files(bucket: str, key: str):
    """AWS CLI loads the values as data from two private files."""
    with TemporaryDirectory(prefix="dataset-parameters-") as directory:
        bucket_path = Path(directory) / "bucket"
        key_path = Path(directory) / "key"
        with bucket_path.open("w", encoding="utf-8") as output:
            output.write(bucket)
        with key_path.open("w", encoding="utf-8") as output:
            output.write(key)
        yield bucket_path.as_uri(), key_path.as_uri()


class S3:
    def __init__(self, bucket: str):
        self.bucket = checked_text(
            bucket, r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", "Bucket invalide.",
        )

    def download(self, key: str, target: Path) -> bool:
        key = checked_key(key)
        target = target.absolute()
        if target.is_symlink():
            raise ValueError("Destination de téléchargement symbolique interdite.")
        with aws_parameter_files(self.bucket, key) as (bucket_file, key_file):
            result = subprocess.run(
                ["aws", "s3api", "get-object", "--bucket", bucket_file, "--key", key_file,
                 str(target), "--output=json", "--no-cli-pager"],
                text=True, capture_output=True, shell=False,
            )
            if result.returncode:
                if any(code in result.stderr for code in ["(NoSuchKey)", "(404)", "(NotFound)"]):
                    return False
                if any(code in result.stderr for code in ["(AccessDenied)", "(403)"]):
                    listing = subprocess.run(
                        ["aws", "s3api", "list-objects-v2", "--bucket", bucket_file,
                         "--prefix", key_file, "--max-keys", "1", "--no-paginate",
                         "--output=json", "--no-cli-pager"],
                        text=True, capture_output=True, shell=False,
                    )
                    if listing.returncode == 0:
                        objects = json.loads(listing.stdout).get("Contents", [])
                        if not any(item.get("Key") == key for item in objects):
                            return False
                raise RuntimeError(f"Lecture S3 impossible pour {key}: {result.stderr.strip()}")
        return True

    def upload_if_absent(self, key: str, source: Path) -> None:
        key = checked_key(key)
        source = source.absolute()
        if source.is_symlink():
            raise ValueError("Source de publication symbolique interdite.")
        with aws_parameter_files(self.bucket, key) as (bucket_file, key_file):
            result = subprocess.run(
                ["aws", "s3api", "put-object", "--bucket", bucket_file, "--key", key_file,
                 "--body=" + str(source), "--if-none-match=*", "--output=json", "--no-cli-pager"],
                text=True, capture_output=True, shell=False,
            )
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
    # Check all three sources before the first remote write.
    for name in NAMES:
        actual = fingerprints(project_path(root, f".data/ml/splits/{name}"))
        if {k: actual[k] for k in ("sha256", "size")} != release["files"][name]:
            raise ValueError(f"{name}: fichier local différent du manifeste.")
    store = store or S3(release["bucket"])
    prefix = f"{PREFIX}/{release['dataset_id']}"
    with TemporaryDirectory(prefix="dataset-publish-") as tmp:
        temporary = Path(tmp)
        for name in NAMES:
            ensure_object(store, f"{prefix}/{name}", project_path(root, f".data/ml/splits/{name}"), temporary)
        checksums = temporary / "sha256.txt"
        # Derive the text from the verified local files, not from the JSON content.
        text = "".join(
            f"{fingerprints(project_path(root, f'.data/ml/splits/{name}'))['sha256']}  {name}\n"
            for name in NAMES
        )
        with checksums.open("w", encoding="utf-8") as output:
            output.write(text)
        ensure_object(store, f"{prefix}/sha256.txt", checksums, temporary)
        # Completeness marker, published only after verifying the three objects.
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
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Racine du projet uniquement.")
    parser.add_argument("--release", type=Path, help=LOCAL_RELEASE + " ou " + DEPLOY_RELEASE)
    parser.add_argument("--output", type=Path, help="Sortie autorisée : " + LOCAL_RELEASE)
    parser.add_argument("--git-revision")
    parser.add_argument("--bucket")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--remote", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = PROJECT_ROOT.resolve()
        if args.root.resolve() != root:
            raise ValueError("--root doit désigner la racine du projet.")
        if args.command == "prepare":
            if not args.output or not args.git_revision:
                parser.error("prepare nécessite --output et --git-revision")
            destination = selected_path(root, args.output, (LOCAL_RELEASE,))
            release = prepare(root, args.git_revision)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                output.write(json_bytes(release))
        else:
            if args.release:
                source = selected_path(root, args.release, (LOCAL_RELEASE, DEPLOY_RELEASE))
                with source.open("rb") as incoming:
                    release = validate_release(json.load(incoming), args.git_revision)
            elif args.command == "publish" and args.bucket:
                # Compatibility with the manual command upload-bootstrap.sh <bucket> [version].
                files = {}
                for name in NAMES:
                    info = fingerprints(project_path(root, f".data/ml/splits/{name}"))
                    files[name] = {k: info[k] for k in ("sha256", "size")}
                revision = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
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
                publish(root, release)
            elif args.remote:
                verify_remote(release)
        print(release["dataset_uri"], flush=True)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Dataset refusé : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
