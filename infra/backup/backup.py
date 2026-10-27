"""Daily MVP backup: PostgreSQL, current S3 objects, then one restore/integrity check."""

import argparse
import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from restore import check_file, restore_databases, validate_archive


def fingerprint(s3, bucket, key, version=None, etag=None, output=None):
    options = {"Bucket": bucket, "Key": key}
    if version:
        options["VersionId"] = version
    if etag:
        options["IfMatch"] = etag
    digest = hashlib.sha256()
    size = 0
    with closing(s3.get_object(**options)["Body"]) as body:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if output:
                output.write(chunk)
    return digest.hexdigest(), size


def protected_object(s3, bucket, key):
    head = s3.head_object(Bucket=bucket, Key=key)
    if (
        head.get("ServerSideEncryption") != "AES256"
        or head.get("ObjectLockMode") != "COMPLIANCE"
        or not head.get("VersionId")
        or head.get("ObjectLockRetainUntilDate", datetime.min.replace(tzinfo=UTC))
        < datetime.now(UTC) + timedelta(days=6)
    ):
        raise RuntimeError(
            f"Missing encryption or seven-day immutable retention: {key}"
        )
    return head


def run_command(session, instance_id, document, run_id):
    ssm = session.client("ssm")
    command = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName=document,
        Parameters={"RunId": [run_id]},
        TimeoutSeconds=900,
    )["Command"]["CommandId"]
    deadline = time.monotonic() + 1900
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            result = ssm.get_command_invocation(
                CommandId=command, InstanceId=instance_id
            )
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if result["Status"] == "Success":
            return
        if result["Status"] not in {"Pending", "InProgress", "Delayed"}:
            # Do not print database/SSM output, which might contain sensitive information.
            raise RuntimeError(f"Backup failed: SSM {command} ({result['Status']})")
    raise TimeoutError(f"Backup timed out: SSM {command}")


def capture_parameters(session, s3, config, prefix):
    """Keep recovery credentials encrypted in S3, never in logs or CI artifacts."""
    ssm = session.client("ssm")
    parameters = []
    for path in config["parameter_paths"]:
        captured = []
        for page in ssm.get_paginator("get_parameters_by_path").paginate(
            Path=path, Recursive=True, WithDecryption=True
        ):
            captured.extend(
                {key: item[key] for key in ("Name", "Type", "Value", "Version")}
                for item in page["Parameters"]
            )
        if not captured:
            raise RuntimeError("No recovery parameters found at " + path)
        parameters.extend(captured)
    parameters.append(
        ssm.get_parameter(Name=config["deployed_sha_parameter"])["Parameter"]
    )
    payload = json.dumps(parameters, default=str).encode()
    digest = hashlib.sha256(payload).hexdigest()
    key = prefix + "config/ssm-parameters.json"
    s3.put_object(
        Bucket=config["bucket"],
        Key=key,
        Body=payload,
        ContentType="application/json",
        ServerSideEncryption="AES256",
        ChecksumAlgorithm="SHA256",
        Metadata={"sha256": digest},
    )


def create(session, config, run_id):
    s3 = session.client("s3")
    bucket = config["bucket"]
    retention = s3.get_object_lock_configuration(Bucket=bucket)[
        "ObjectLockConfiguration"
    ]
    if retention.get("Rule", {}).get("DefaultRetention") != {
        "Mode": "COMPLIANCE",
        "Days": 7,
    }:
        raise RuntimeError("Expected COMPLIANCE default retention of seven days")
    run_command(session, config["instance_id"], config["document"], run_id)
    for host in config["log_hosts"]:
        run_command(session, host["instance_id"], host["document"], run_id)
    entries = []
    prefix = f"runs/{run_id}/"
    capture_parameters(session, s3, config, prefix)
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix
    ):
        for obj in page.get("Contents", []):
            head = protected_object(s3, bucket, obj["Key"])
            # The hash was computed locally on the EC2 before the upload.
            entries.append(
                {
                    "key": obj["Key"],
                    "version": head["VersionId"],
                    "sha256": head["Metadata"]["sha256"],
                    "size": head["ContentLength"],
                }
            )
    if not any(item["key"].endswith("/databases.json") for item in entries):
        raise RuntimeError("Database backup metadata is missing")
    for host in config["log_hosts"]:
        if not any(
            item["key"] == prefix + "logs/" + host["name"] + "/logs.json"
            for item in entries
        ):
            raise RuntimeError("Missing log backup for " + host["name"])
    transfer = TransferConfig(max_concurrency=2)
    for source in config["sources"]:
        count = 0
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=source["bucket"], Prefix=source["prefix"]
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if source.get("key") and key != source["key"]:
                    continue
                head = s3.head_object(Bucket=source["bucket"], Key=key)
                version = head.get("VersionId")
                digest, size = fingerprint(
                    s3, source["bucket"], key, version, head["ETag"]
                )
                target = (
                    prefix
                    + "s3/"
                    + hashlib.sha256(
                        (source["bucket"] + "/" + key).encode()
                    ).hexdigest()
                )
                copy_source = {"Bucket": source["bucket"], "Key": key}
                if version:
                    copy_source["VersionId"] = version
                s3.copy(
                    copy_source,
                    bucket,
                    target,
                    Config=transfer,
                    ExtraArgs={
                        "ServerSideEncryption": "AES256",
                        "CopySourceIfMatch": head["ETag"],
                    },
                )
                copied = protected_object(s3, bucket, target)
                entries.append(
                    {
                        "key": target,
                        "version": copied["VersionId"],
                        "sha256": digest,
                        "size": size,
                        "source": copy_source,
                    }
                )
                count += 1
        if count == 0:
            raise RuntimeError(
                f"Source contains no objects: {source['bucket']}/{source['prefix']}"
            )
    manifest = {
        "schema": 1,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "objects": entries,
    }
    key = prefix + "manifest.json"
    response = s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
        ChecksumAlgorithm="SHA256",
    )
    protected_object(s3, bucket, key)
    return key, response["VersionId"]


def verify(session, bucket, key, version):
    s3 = session.client("s3")
    # Explicit versions protect restores from later overwrites/delete markers.
    with s3.get_object(Bucket=bucket, Key=key, VersionId=version)["Body"] as body:
        manifest = json.load(body)
    if manifest["schema"] != 1:
        raise ValueError("Unsupported backup manifest")
    with tempfile.TemporaryDirectory(prefix="enervision-restore-") as temporary:
        directory = Path(temporary)
        for entry in manifest["objects"]:
            output = None
            if "/db/" in entry["key"]:
                output = (directory / Path(entry["key"]).name).open("wb")
            elif "/logs/" in entry["key"] or "/config/" in entry["key"]:
                # A flat hash avoids local filename collisions between hosts.
                output = (
                    directory / hashlib.sha256(entry["key"].encode()).hexdigest()
                ).open("wb")
            try:
                digest, size = fingerprint(
                    s3, bucket, entry["key"], entry["version"], output=output
                )
            finally:
                if output:
                    output.close()
            if (digest, size) != (entry["sha256"], entry["size"]):
                raise ValueError(f"Corrupted backup: {entry['key']}")
            if output and "/db/" not in entry["key"]:
                validate_archive(Path(output.name), entry["key"])
        metadata = json.loads((directory / "databases.json").read_text())
        for database in metadata["databases"]:
            filename = database["file"]
            if Path(filename).name != filename:
                raise ValueError("Invalid database filename")
            entry = next(
                item
                for item in manifest["objects"]
                if item["key"].endswith("/db/" + filename)
            )
            check_file(directory / filename, entry["sha256"])
        count = restore_databases(directory)
    print(f"Integrity OK: {len(manifest['objects'])} files; {count} databases restored")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify"])
    parser.add_argument("--manifest", help="Manifest key (verify)")
    parser.add_argument("--version", help="Manifest version ID (verify)")
    parser.add_argument("--region", default="eu-west-3")
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    config = json.loads(
        session.client("ssm").get_parameter(Name="/enervision/prod/backup")[
            "Parameter"
        ]["Value"]
    )
    if args.action == "create":
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        key, version = create(session, config, run_id)
        print(f"Backup: s3://{config['bucket']}/{key} version={version}")
        # The manifest remains available for investigation even when verification fails.
        verify(session, config["bucket"], key, version)
    else:
        if not args.manifest or not args.version:
            parser.error("verify requires --manifest and --version")
        verify(session, config["bucket"], args.manifest, args.version)


if __name__ == "__main__":
    main()
