"""A single integration test, using disposable local databases and no AWS access."""

import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dump_db import dump_databases, sql
from dump_host import dump_host, export_loki
from restore import check_file, restore_databases, validate_archive


class BackupIntegrityTest(unittest.TestCase):
    def test_restore_and_detect_corruption(self):
        container = "enervision-backup-test-" + uuid.uuid4().hex[:12]
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container,
                    "--network",
                    "none",
                    "--memory",
                    "1g",
                    "--cpus",
                    "2",
                    "--label",
                    "com.docker.compose.project=" + container,
                    "--label",
                    "com.docker.compose.service=db",
                    "-e",
                    "POSTGRES_USER=enervision",
                    "-e",
                    "POSTGRES_DB=enervision",
                    "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "timescale/timescaledb:2.17.2-pg16",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            for _ in range(90):
                if (
                    subprocess.run(
                        [
                            "docker",
                            "exec",
                            container,
                            "pg_isready",
                            "-h",
                            "127.0.0.1",
                            "-U",
                            "enervision",
                        ],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(1)
            else:
                subprocess.run(
                    ["docker", "logs", "--tail", "30", container], check=False
                )
                self.fail("Source database did not become ready")
            sql(
                container,
                """
                CREATE EXTENSION IF NOT EXISTS timescaledb;
                CREATE TABLE readings(ts timestamptz NOT NULL, value double precision,
                  PRIMARY KEY(ts));
                SELECT create_hypertable('readings', 'ts');
                INSERT INTO readings SELECT '2026-10-01'::timestamptz + n * interval '1 hour',
                  n * 1.5 FROM generate_series(1, 100) n;
                CREATE TABLE users(id int PRIMARY KEY, email text UNIQUE);
                INSERT INTO users VALUES (1, 'restore@example.invalid');
                CREATE ROLE monitoring LOGIN;
                GRANT SELECT ON users TO monitoring;
            """,
                "enervision",
            )
            sql(container, "CREATE DATABASE mlflow TEMPLATE template0")
            sql(
                container,
                "CREATE TABLE experiments(id int PRIMARY KEY, name text);"
                "INSERT INTO experiments VALUES (1, 'integrity-check')",
                "mlflow",
            )
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                metadata = dump_databases(directory, container)
                self.assertEqual(
                    {db["name"] for db in metadata["databases"]},
                    {"enervision", "postgres", "mlflow"},
                )
                hashes = {
                    path: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in directory.iterdir()
                }
                for path, digest in hashes.items():
                    check_file(path, digest)
                self.assertEqual(restore_databases(directory), 3)
                dump = next(path for path in hashes if path.suffix == ".dump")
                with dump.open("r+b") as stream:
                    stream.write(b"CORRUPTED")
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    check_file(dump, hashes[dump])
                # Log archives are checked by the same integrity run as database dumps.
                values = [
                    [str(timestamp), "event-" + str(timestamp)]
                    for timestamp in range(0, 120, 10)
                ]

                def fetch_logs(start, end, limit):
                    return [
                        {
                            "stream": {"machine": "app"},
                            "values": [
                                value
                                for value in values
                                if start <= int(value[0]) < end
                            ][:limit],
                        }
                    ]

                exported = io.StringIO()
                self.assertEqual(export_loki(0, 120, exported, fetch_logs, limit=3), 12)
                self.assertEqual(
                    {
                        json.loads(line)["timestamp_ns"]
                        for line in exported.getvalue().splitlines()
                    },
                    {value[0] for value in values},
                )
                archive = directory / "loki.jsonl.gz"
                archive.write_bytes(gzip.compress(exported.getvalue().encode()))
                validate_archive(archive, archive.name)
                data = bytearray(archive.read_bytes())
                data[-8] ^= 0xFF
                archive.write_bytes(data)
                with self.assertRaises(OSError):
                    validate_archive(archive, archive.name)

                def saturated_logs(start, end, limit):
                    return [{"stream": {"machine": "app"}, "values": values[:limit]}]

                with self.assertRaisesRegex(RuntimeError, "truncated"):
                    export_loki(0, 1, io.StringIO(), saturated_logs, limit=3)
                logs = directory / "logs"
                logs.mkdir()
                real_popen = subprocess.Popen

                def journal_fixture(command, **kwargs):
                    if command[0] == "journalctl":
                        return SimpleNamespace(
                            stdout=io.BytesIO(b'{"MESSAGE":"test system event"}\n'),
                            wait=lambda: 0,
                        )
                    return real_popen(command, **kwargs)

                # Read only the fixture container's logs, never the developer host journal.
                with patch("dump_host.subprocess.Popen", side_effect=journal_fixture):
                    dump_host(logs, "app", container)
                metadata = json.loads((logs / "logs.json").read_text())
                self.assertEqual(len(metadata["containers"]), 1)
                for path in logs.iterdir():
                    validate_archive(path, path.name)
        finally:
            subprocess.run(
                ["docker", "rm", "-fv", container],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    unittest.main()
