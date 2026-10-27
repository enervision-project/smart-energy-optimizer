"""Backup orchestration and failure tests; AWS is replaced by versioned in-memory storage."""

import gzip
import hashlib
import io
import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import backup
from botocore.response import StreamingBody


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.retention = {"Mode": "COMPLIANCE", "Days": 7}
        self.copies = []

    def put_object(self, Bucket, Key, Body, **options):
        version = str(len(self.objects) + 1)
        body = Body.encode() if isinstance(Body, str) else Body
        self.objects[Bucket, Key] = {
            "Body": body,
            "VersionId": version,
            "ETag": '"etag"',
            "Metadata": options.get("Metadata", {}),
            "ServerSideEncryption": "AES256",
            "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": datetime.now(UTC) + timedelta(days=7),
            "ContentLength": len(body),
        }
        return {"VersionId": version}

    def head_object(self, Bucket, Key):
        return self.objects[Bucket, Key].copy()

    def get_object(self, Bucket, Key, VersionId=None, IfMatch=None):
        obj = self.objects[Bucket, Key]
        if VersionId and VersionId != obj.get("VersionId"):
            raise ValueError("Wrong object version")
        if IfMatch and IfMatch != obj["ETag"]:
            raise ValueError("Source changed")
        return {"Body": StreamingBody(io.BytesIO(obj["Body"]), len(obj["Body"]))}

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"

        def paginate(Bucket, Prefix):
            # One object per page exercises pagination rather than a single response.
            for bucket, key in list(self.objects):
                if bucket == Bucket and key.startswith(Prefix):
                    yield {"Contents": [{"Key": key}]}
            yield {}

        return SimpleNamespace(paginate=paginate)

    def get_object_lock_configuration(self, Bucket):
        return {
            "ObjectLockConfiguration": {"Rule": {"DefaultRetention": self.retention}}
        }

    def copy(self, source, bucket, key, **options):
        self.copies.append((source, options))
        obj = self.get_object(
            **source, IfMatch=options["ExtraArgs"]["CopySourceIfMatch"]
        )
        self.put_object(Bucket=bucket, Key=key, Body=obj["Body"].read())


class InvocationDoesNotExist(Exception):
    pass


class MemorySSM:
    exceptions = SimpleNamespace(InvocationDoesNotExist=InvocationDoesNotExist)

    def __init__(self):
        self.commands = []
        self.parameters = [
            {
                "Name": "/prod/password",
                "Type": "SecureString",
                "Value": "fixture-secret",
                "Version": 1,
            }
        ]

    def send_command(self, **options):
        self.commands.append(options)
        return {"Command": {"CommandId": "command-id"}}

    def get_command_invocation(self, **options):
        return {"Status": "Success"}

    def get_paginator(self, operation):
        assert operation == "get_parameters_by_path"
        return SimpleNamespace(
            paginate=lambda **options: [{"Parameters": self.parameters}]
        )

    def get_parameter(self, Name):
        return {
            "Parameter": {
                "Name": Name,
                "Value": "deployed-sha",
                "Type": "String",
                "Version": 1,
            }
        }


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.s3, self.ssm = MemoryS3(), MemorySSM()
        self.session = SimpleNamespace(
            client=lambda service: self.s3 if service == "s3" else self.ssm
        )
        self.config = {
            "bucket": "backups",
            "instance_id": "i-app",
            "document": "dump",
            "parameter_paths": ["/prod/env"],
            "deployed_sha_parameter": "/prod/sha",
            "log_hosts": [{"name": "app", "instance_id": "i-app", "document": "logs"}],
            "sources": [{"bucket": "source", "prefix": "state", "key": "state"}],
        }
        self.prefix = "runs/run/"
        self.payloads = {
            "db/databases.json": json.dumps(
                {"databases": [{"name": "app", "file": "database-0.dump"}]}
            ).encode(),
            "db/database-0.dump": b"database contents",
            "db/globals.sql": b"roles",
            "logs/app/logs.json": b"{}",
            "logs/app/journal.jsonl.gz": gzip.compress(b'{"MESSAGE":"fixture"}\n'),
        }
        for key, body in self.payloads.items():
            self.s3.put_object(
                Bucket="backups",
                Key=self.prefix + key,
                Body=body,
                Metadata={"sha256": hashlib.sha256(body).hexdigest()},
            )
        self.s3.put_object(Bucket="source", Key="state", Body=b"source state")
        self.s3.put_object(Bucket="source", Key="state.tflock", Body=b"skip lock")

    def create(self):
        with patch("backup.time.sleep"):
            return backup.create(self.session, self.config, "run")

    def test_round_trip_and_corrupted_backup(self):
        key, version = self.create()
        self.assertEqual(len(self.ssm.commands), 2)
        self.assertEqual(len(self.s3.copies), 1)
        self.assertIn("VersionId", self.s3.copies[0][0])
        with patch("backup.restore_databases", return_value=1) as restore:
            backup.verify(self.session, "backups", key, version)
            restore.assert_called_once()
        self.s3.objects["backups", self.prefix + "db/database-0.dump"]["Body"] = (
            b"corrupted"
        )
        with (
            self.assertRaisesRegex(ValueError, "Corrupted backup"),
            patch("backup.restore_databases") as restore,
        ):
            backup.verify(self.session, "backups", key, version)
            restore.assert_not_called()

    def test_copy_unversioned_source_and_check_source_hash(self):
        del self.s3.objects["source", "state"]["VersionId"]
        key, version = self.create()
        self.assertNotIn("VersionId", self.s3.copies[0][0])
        manifest = json.loads(
            self.s3.get_object(Bucket="backups", Key=key, VersionId=version)[
                "Body"
            ].read()
        )
        copied = next(item for item in manifest["objects"] if "source" in item)
        self.assertEqual(copied["sha256"], hashlib.sha256(b"source state").hexdigest())

    def test_rejects_wrong_retention_and_missing_uploads(self):
        self.s3.retention["Days"] = 1
        with self.assertRaisesRegex(RuntimeError, "seven days"):
            self.create()
        self.s3.retention["Days"] = 7
        del self.s3.objects["backups", self.prefix + "logs/app/logs.json"]
        with self.assertRaisesRegex(RuntimeError, "Missing log"):
            self.create()
        del self.s3.objects["backups", self.prefix + "db/databases.json"]
        with self.assertRaisesRegex(RuntimeError, "metadata is missing"):
            self.create()

    def test_rejects_empty_source_and_empty_parameter_path(self):
        self.config["sources"][0]["key"] = "missing"
        with self.assertRaisesRegex(RuntimeError, "Source contains no objects"):
            self.create()
        self.ssm.parameters = []
        with self.assertRaisesRegex(RuntimeError, "No recovery parameters"):
            self.create()

    def test_rejects_unprotected_objects(self):
        obj = self.s3.objects["source", "state"]
        for field, value in [
            ("ServerSideEncryption", "none"),
            ("ObjectLockMode", "GOVERNANCE"),
            ("VersionId", None),
            ("ObjectLockRetainUntilDate", datetime.now(UTC)),
        ]:
            with (
                self.subTest(field=field),
                patch.dict(obj, {field: value}),
                self.assertRaisesRegex(RuntimeError, "Missing encryption"),
            ):
                backup.protected_object(self.s3, "source", "state")

    def test_ssm_polling_failure_and_timeout(self):
        statuses = [
            InvocationDoesNotExist(),
            {"Status": "Pending"},
            {"Status": "Success"},
        ]
        with (
            patch.object(self.ssm, "get_command_invocation", side_effect=statuses),
            patch("backup.time.sleep"),
        ):
            backup.run_command(self.session, "i-app", "doc", "run")
        with (
            patch.object(
                self.ssm, "get_command_invocation", return_value={"Status": "Failed"}
            ),
            patch("backup.time.sleep"),
            self.assertRaisesRegex(RuntimeError, "Failed"),
        ):
            backup.run_command(self.session, "i-app", "doc", "run")
        with (
            patch("backup.time.monotonic", side_effect=[0, 1901]),
            self.assertRaises(TimeoutError),
        ):
            backup.run_command(self.session, "i-app", "doc", "run")

    def test_rejects_unknown_manifest_and_unsafe_database_path(self):
        key, version = self.create()
        manifest = self.s3.objects["backups", key]
        body = json.loads(manifest["Body"])
        body["schema"] = 2
        manifest["Body"] = json.dumps(body).encode()
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            backup.verify(self.session, "backups", key, version)
        body["schema"] = 1
        metadata_key = self.prefix + "db/databases.json"
        metadata = json.dumps({"databases": [{"file": "../unsafe"}]}).encode()
        self.s3.objects["backups", metadata_key]["Body"] = metadata
        for entry in body["objects"]:
            if entry["key"] == metadata_key:
                entry.update(
                    sha256=hashlib.sha256(metadata).hexdigest(), size=len(metadata)
                )
        manifest["Body"] = json.dumps(body).encode()
        with self.assertRaisesRegex(ValueError, "Invalid database filename"):
            backup.verify(self.session, "backups", key, version)

    def test_cli_create_verify_and_required_arguments(self):
        self.ssm.get_parameter = Mock(
            return_value={"Parameter": {"Value": json.dumps(self.config)}}
        )
        for arguments in [
            ["backup.py", "create"],
            ["backup.py", "verify", "--manifest", "key", "--version", "v1"],
        ]:
            with (
                patch("backup.boto3.Session", return_value=self.session),
                patch("sys.argv", arguments),
                patch("backup.create", return_value=("key", "v1")),
                patch("backup.verify") as verify,
                patch("backup.os.umask"),
            ):
                backup.main()
                verify.assert_called_once_with(self.session, "backups", "key", "v1")
        with (
            patch("backup.boto3.Session", return_value=self.session),
            patch("sys.argv", ["backup.py", "verify"]),
            patch("backup.os.umask"),
            patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit),
        ):
            backup.main()


if __name__ == "__main__":
    unittest.main()
