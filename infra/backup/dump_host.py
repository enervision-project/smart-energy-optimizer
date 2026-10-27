"""Export the previous 24 hours of host, container and Loki logs without stopping services."""

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def fetch_loki(start, end, limit):
    query = urlencode(
        {
            "query": '{machine=~".+"}',
            "start": str(start),
            "end": str(end),
            "direction": "forward",
            "limit": limit,
        }
    )
    # Loopback only, on the monitoring host; no new network exposure.
    with urlopen(
        "http://127.0.0.1:3100/loki/api/v1/query_range?" + query, timeout=60
    ) as response:
        result = json.load(response)
    if result["status"] != "success" or result["data"]["resultType"] != "streams":
        raise RuntimeError("Loki log export failed")
    return result["data"]["result"]


def export_loki(start, end, stream, fetch=fetch_loki, limit=1000):
    """Split saturated windows to avoid silently truncating at Loki's result limit."""
    results = fetch(start, end, limit)
    count = sum(len(item["values"]) for item in results)
    if count >= limit:
        if end - start <= 1:
            raise RuntimeError(
                "Too many Loki entries at one timestamp; export would be truncated"
            )
        middle = (start + end) // 2
        return export_loki(start, middle, stream, fetch, limit) + export_loki(
            middle, end, stream, fetch, limit
        )
    written = 0
    for item in results:
        for timestamp, line in item["values"]:
            if start <= int(timestamp) < end:
                stream.write(
                    json.dumps(
                        {
                            "labels": item["stream"],
                            "timestamp_ns": timestamp,
                            "line": line,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
    return written


def dump_host(directory, host, project, include_loki=False):
    end = datetime.now(timezone.utc)  # noqa: UP017 -- AL2023 ships Python 3.9.
    start = end - timedelta(days=1)
    since, until = start.isoformat(), end.isoformat()
    # Journalctl supports UTC timestamps; require successful export rather than hiding errors.
    with gzip.open(directory / "journal.jsonl.gz", "wb") as stream:
        process = subprocess.Popen(
            [
                "journalctl",
                "--since",
                start.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "--until",
                end.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "--output=json",
                "--no-pager",
                "--quiet",
            ],
            stdout=subprocess.PIPE,
        )
        try:
            shutil.copyfileobj(process.stdout, stream, length=1024 * 1024)
        finally:
            process.stdout.close()
            code = process.wait()
        if code:
            raise RuntimeError("Journal export failed")
    containers = []
    ids = subprocess.check_output(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--format",
            "{{.ID}}",
        ],
        text=True,
    ).split()
    if not ids:
        raise RuntimeError("No project containers found for host backup")
    for container in ids:
        details = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "--format",
                    (
                        '{"name":{{json .Name}},"image":{{json .Config.Image}},'
                        '"service":{{json (index .Config.Labels "com.docker.compose.service")}}}'
                    ),
                    container,
                ],
                text=True,
            )
        )
        filename = "docker-" + container + ".log.gz"
        # Docker logs writes to both stdout and stderr. Merge both in the private archive.
        with gzip.open(directory / filename, "wb") as stream:
            process = subprocess.Popen(
                [
                    "docker",
                    "logs",
                    "--timestamps",
                    "--since",
                    since,
                    "--until",
                    until,
                    container,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                shutil.copyfileobj(process.stdout, stream, length=1024 * 1024)
            finally:
                process.stdout.close()
                code = process.wait()
            if code:
                raise RuntimeError("Container log export failed")
        containers.append(dict(details, file=filename))
    metadata = {"host": host, "start": since, "end": until, "containers": containers}
    if include_loki:
        with gzip.open(directory / "loki.jsonl.gz", "wt", encoding="utf-8") as stream:
            metadata["loki_entries"] = export_loki(
                int(start.timestamp() * 1_000_000_000),
                int(end.timestamp() * 1_000_000_000),
                stream,
            )
    (directory / "logs.json").write_text(json.dumps(metadata), encoding="utf-8")


def main():
    os.umask(0o077)
    host = os.environ["BACKUP_HOST"]
    bucket = os.environ["BACKUP_BUCKET"]
    run_id = os.environ["BACKUP_RUN_ID"]
    with tempfile.TemporaryDirectory(prefix="enervision-log-backup-") as temporary:
        directory = Path(temporary)
        dump_host(
            directory,
            host,
            os.environ["BACKUP_PROJECT"],
            include_loki=(host == "monitoring"),
        )
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
                    f"s3://{bucket}/runs/{run_id}/logs/{host}/{path.name}",
                    "--only-show-errors",
                    "--sse",
                    "AES256",
                    "--checksum-algorithm",
                    "SHA256",
                    "--metadata",
                    "sha256=" + digest.hexdigest(),
                ],
                check=True,
            )
    print("Host logs uploaded")


if __name__ == "__main__":
    main()
