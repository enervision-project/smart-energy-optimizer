"""One integrity check: hashes plus a complete restore in an isolated TimescaleDB."""

import gzip
import hashlib
import json
import subprocess
import time
import uuid


def validate_archive(path, key):
    if key.endswith(".gz"):
        # Reading through EOF also checks the gzip trailer/CRC, beyond SHA-256.
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if key.endswith(".jsonl.gz"):
                    json.loads(line)
    elif key.endswith(".json"):
        with path.open(encoding="utf-8") as stream:
            json.load(stream)


def check_file(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}")


def restore_databases(directory):
    metadata = json.loads((directory / "databases.json").read_text())
    requested_image = metadata["image"]
    # Only reviewed project versions are allowed; no file-controlled command argument.
    if requested_image in (
        "timescale/timescaledb:2.17.2-pg16",
        "docker.io/timescale/timescaledb:2.17.2-pg16",
    ):
        image = "docker.io/timescale/timescaledb:2.17.2-pg16"
    elif requested_image in (
        "timescale/timescaledb:2.30.2-pg16",
        "docker.io/timescale/timescaledb:2.30.2-pg16",
    ):
        image = "docker.io/timescale/timescaledb:2.30.2-pg16"
    else:
        raise ValueError("Expected the project TimescaleDB image")
    name = f"enervision-restore-{uuid.uuid4().hex[:12]}"

    def execute(*args, **kwargs):
        return subprocess.run(
            ["docker", "exec", "-i", name, *args], check=True, **kwargs
        )

    def sql(database, statement):
        return execute(
            "psql",
            "-X",
            "-U",
            "backup_restore",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            statement,
            capture_output=True,
            text=True,
        ).stdout.strip()

    try:
        # No published ports, no access to prod networks, no production volumes.
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                "none",
                "--memory",
                "1g",
                "--cpus",
                "2",
                "-e",
                "POSTGRES_USER=backup_restore",
                "-e",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                image,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for _ in range(90):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "backup_restore",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Restore database did not become ready")
        with (directory / "globals.sql").open("rb") as stream:
            execute(
                "psql",
                "-X",
                "-U",
                "backup_restore",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                stdin=stream,
                stdout=subprocess.DEVNULL,
            )
        for database in metadata["databases"]:
            db = database["name"]
            if db != "postgres":
                execute(
                    "createdb",
                    "-U",
                    "backup_restore",
                    "--owner",
                    database["owner"],
                    "--",
                    db,
                )
            if database["timescaledb"]:
                # Versions come from PostgreSQL; still quote SQL literals explicitly.
                version = database["timescaledb"].replace("'", "''")
                sql(
                    db,
                    f"CREATE EXTENSION IF NOT EXISTS timescaledb VERSION '{version}'",
                )
                sql(db, "SELECT timescaledb_pre_restore()")
            with (directory / database["file"]).open("rb") as stream:
                execute(
                    "pg_restore",
                    "-U",
                    "backup_restore",
                    "-d",
                    db,
                    "--exit-on-error",
                    stdin=stream,
                    stdout=subprocess.DEVNULL,
                )
            if database["timescaledb"]:
                sql(db, "SELECT timescaledb_post_restore()")
            # Reads every ordinary table; amcheck additionally checks supported indexes.
            # This detects unreadable data; amcheck additionally checks supported indexes.
            sql(
                db,
                """DO $$ DECLARE r record; BEGIN
                FOR r IN SELECT n.nspname, c.relname FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE c.relkind = 'r' AND n.nspname NOT LIKE 'pg_%'
                  AND n.nspname <> 'information_schema'
                LOOP EXECUTE format(
                  'SELECT sum(octet_length(row_to_json(t)::text)) FROM %I.%I t',
                  r.nspname, r.relname);
                END LOOP; END $$""",
            )
            execute(
                "pg_amcheck",
                "-U",
                "backup_restore",
                "--install-missing",
                "-d",
                db,
                stdout=subprocess.DEVNULL,
            )
        return len(metadata["databases"])
    finally:
        subprocess.run(
            ["docker", "rm", "-fv", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
