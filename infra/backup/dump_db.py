"""Dump all application databases on the EC2; only the stdlib and AWS CLI are needed."""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def docker(container, *args, **kwargs):
    return subprocess.run(
        ["docker", "exec", "-i", container, *args], check=True, **kwargs
    )


def sql(container, query, database="postgres"):
    return docker(
        container,
        "sh",
        "-c",
        'exec psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$1" -c "$2"',
        "query",
        database,
        query,
        capture_output=True,
        text=True,
    ).stdout.strip()


def dump_databases(directory, container):
    """Custom-format dumps, roles, and exact engine versions for an isolated restore."""
    databases = json.loads(
        sql(
            container,
            """
        SELECT json_agg(json_build_object('name', datname,
          'owner', pg_get_userbyid(datdba))) FROM pg_database
        WHERE NOT datistemplate AND datallowconn
    """,
        )
    )
    for index, database in enumerate(databases):
        database["file"] = f"database-{index}.dump"
        database["timescaledb"] = sql(
            container,
            "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'",
            database["name"],
        )
        with (directory / database["file"]).open("wb") as stream:
            docker(
                container,
                "sh",
                "-c",
                'exec pg_dump -U "$POSTGRES_USER" -Fc -d "$1"',
                "dump",
                database["name"],
                stdout=stream,
            )
    with (directory / "globals.sql").open("wb") as stream:
        docker(
            container,
            "sh",
            "-c",
            'exec pg_dumpall -U "$POSTGRES_USER" --globals-only',
            stdout=stream,
        )
    image = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container], text=True
    ).strip()
    metadata = {"image": image, "databases": databases}
    (directory / "databases.json").write_text(json.dumps(metadata), encoding="utf-8")
    return metadata


def main():
    os.umask(0o077)
    bucket = os.environ["BACKUP_BUCKET"]
    run_id = os.environ["BACKUP_RUN_ID"]
    container = subprocess.check_output(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=enervision",
            "--filter",
            "label=com.docker.compose.service=db",
            "--format",
            "{{.ID}}",
        ],
        text=True,
    ).strip()
    if not container or "\n" in container:
        raise RuntimeError("Expected exactly one running enervision database")
    with tempfile.TemporaryDirectory(prefix="enervision-backup-") as temporary:
        directory = Path(temporary)
        dump_databases(directory, container)
        for path in sorted(directory.iterdir()):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            subprocess.run(
                [
                    "aws",
                    "s3",
                    "cp",
                    str(path),
                    f"s3://{bucket}/runs/{run_id}/db/{path.name}",
                    "--only-show-errors",
                    "--sse",
                    "AES256",
                    "--checksum-algorithm",
                    "SHA256",
                    "--metadata",
                    f"sha256={digest.hexdigest()}",
                ],
                check=True,
            )
    print("Database dumps uploaded")


if __name__ == "__main__":
    main()
