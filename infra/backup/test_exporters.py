"""Host exporter failures, encrypted uploads and restore cleanup, without production access."""

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dump_db
import dump_host
import restore


class ExporterTest(unittest.TestCase):
    def test_loki_http_success_and_failure(self):
        for status in ("success", "error"):
            payload = {
                "status": status,
                "data": {"resultType": "streams", "result": []},
            }
            with patch(
                "dump_host.urlopen",
                return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                if status == "success":
                    self.assertEqual(dump_host.fetch_loki(0, 100, 10), [])
                else:
                    with self.assertRaisesRegex(RuntimeError, "Loki log export failed"):
                        dump_host.fetch_loki(0, 100, 10)

    def test_host_export_checks_process_errors_and_captures_loki(self):
        cases = [
            (1, 0, "id", "Journal export failed"),
            (0, 0, "", "No project containers"),
            (0, 1, "id", "Container log export failed"),
            (0, 0, "id", None),
        ]
        for journal_code, docker_code, ids, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                processes = [
                    SimpleNamespace(
                        stdout=io.BytesIO(b'{"MESSAGE":"ok"}\n'),
                        wait=lambda code=journal_code: code,
                    ),
                    SimpleNamespace(
                        stdout=io.BytesIO(b"container event\n"),
                        wait=lambda code=docker_code: code,
                    ),
                ]

                def export(start, end, stream):
                    stream.write('{"line":"loki event"}\n')
                    return 1

                with (
                    patch("dump_host.subprocess.Popen", side_effect=processes),
                    patch(
                        "dump_host.subprocess.check_output",
                        side_effect=[ids, '{"name":"db","image":"image"}'],
                    ),
                    patch("dump_host.export_loki", side_effect=export),
                ):
                    if error:
                        with self.assertRaisesRegex(RuntimeError, error):
                            dump_host.dump_host(
                                directory, "monitoring", "project", include_loki=True
                            )
                    else:
                        dump_host.dump_host(
                            directory, "monitoring", "project", include_loki=True
                        )
                        self.assertEqual(
                            json.loads((directory / "logs.json").read_text())[
                                "loki_entries"
                            ],
                            1,
                        )
                        for path in directory.iterdir():
                            restore.validate_archive(path, path.name)

    def test_database_upload_hash_encryption_and_container_validation(self):
        payload = b"fixture database dump"

        def dump(directory, container):
            (directory / "database.dump").write_bytes(payload)

        with (
            patch.dict(
                "os.environ", {"BACKUP_BUCKET": "backups", "BACKUP_RUN_ID": "run"}
            ),
            patch("dump_db.subprocess.check_output", return_value="container"),
            patch("dump_db.dump_databases", side_effect=dump),
            patch("dump_db.subprocess.run") as upload,
            patch("dump_db.os.umask"),
        ):
            dump_db.main()
            command = upload.call_args.args[0]
            self.assertIn("AES256", command)
            self.assertIn("sha256=" + hashlib.sha256(payload).hexdigest(), command)
        for containers in ("", "one\ntwo"):
            with (
                patch.dict(
                    "os.environ", {"BACKUP_BUCKET": "backups", "BACKUP_RUN_ID": "run"}
                ),
                patch("dump_db.subprocess.check_output", return_value=containers),
                patch("dump_db.os.umask"),
                self.assertRaisesRegex(RuntimeError, "exactly one"),
            ):
                dump_db.main()

    def test_log_upload_hash_and_encryption(self):
        payload = b"log archive"

        def dump(directory, host, project, include_loki):
            self.assertTrue(include_loki)
            (directory / "journal.gz").write_bytes(payload)

        with (
            patch.dict(
                "os.environ",
                {
                    "BACKUP_BUCKET": "backups",
                    "BACKUP_RUN_ID": "run",
                    "BACKUP_HOST": "monitoring",
                    "BACKUP_PROJECT": "project",
                },
            ),
            patch("dump_host.dump_host", side_effect=dump),
            patch("dump_host.subprocess.run") as upload,
            patch("dump_host.os.umask"),
        ):
            dump_host.main()
            command = upload.call_args.args[0]
            self.assertIn("AES256", command)
            self.assertIn("s3://backups/runs/run/logs/monitoring/journal.gz", command)
            self.assertIn("sha256=" + hashlib.sha256(payload).hexdigest(), command)

    def test_failed_restore_cleans_up_container(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            metadata = directory / "databases.json"
            metadata.write_text('{"image":"untrusted/image:latest"}')
            with self.assertRaisesRegex(ValueError, "TimescaleDB image"):
                restore.restore_databases(directory)
            metadata.write_text('{"image":"timescale/timescaledb:2.17.2-pg16"}')
            with (
                patch(
                    "restore.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 1),
                ) as command,
                patch("restore.time.sleep"),
                self.assertRaisesRegex(RuntimeError, "did not become ready"),
            ):
                restore.restore_databases(directory)
            self.assertEqual(command.call_args.args[0][:3], ["docker", "rm", "-fv"])

    def test_restore_allows_only_reviewed_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            metadata = directory / "databases.json"
            for image in [
                "timescale/timescaledb:latest",
                "timescale/timescaledb:2.17.2-pg16 --privileged",
                "timescale/timescaledb:2.17.2-pg16\n--mount=/host",
                "--privileged",
                "attacker.example/timescale/timescaledb:2.17.2-pg16",
            ]:
                metadata.write_text(json.dumps({"image": image}))
                with (
                    self.subTest(image=image),
                    patch("restore.subprocess.run") as command,
                    self.assertRaisesRegex(ValueError, "TimescaleDB image"),
                ):
                    restore.restore_databases(directory)
                command.assert_not_called()
            for version in ("2.17.2-pg16", "2.30.2-pg16"):
                for registry in ("", "docker.io/"):
                    metadata.write_text(
                        json.dumps(
                            {"image": registry + "timescale/timescaledb:" + version}
                        )
                    )
                    with (
                        self.subTest(version=version, registry=registry),
                        patch(
                            "restore.subprocess.run",
                            return_value=subprocess.CompletedProcess([], 1),
                        ) as command,
                        patch("restore.time.sleep"),
                        self.assertRaisesRegex(RuntimeError, "did not become ready"),
                    ):
                        restore.restore_databases(directory)
                    self.assertEqual(
                        command.call_args_list[0].args[0][-1],
                        "docker.io/timescale/timescaledb:" + version,
                    )
