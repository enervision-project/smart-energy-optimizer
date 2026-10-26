"""Bronze : archivage S3 des mesures telles que reçues de l'API énergie."""

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import boto3


def write_readings_bronze(
    readings: Sequence[Mapping[str, Any]],
    bucket: str | None = None,
    *,
    client: Any = None,
    collected_at: datetime | None = None,
) -> str | None:
    """Archive les JSON d'origine ; seul le classement utilise l'heure de collecte.

    Chaque réponse garde son propre timestamp exact, ses NULL et tous ses champs.
    Une clé précise à la microseconde évite d'écraser deux collectes d'une même
    minute. Sans BRONZE_BUCKET, rien n'est écrit.
    """
    bucket_name = (
        bucket if bucket is not None else os.environ.get("BRONZE_BUCKET", "")
    ).strip()
    if not bucket_name or not readings:
        return None

    captured_at = collected_at if collected_at is not None else datetime.now(UTC)
    if captured_at.utcoffset() is None:
        raise ValueError("collected_at doit comporter un fuseau horaire.")
    captured_at = captured_at.astimezone(UTC)
    key = (
        f"bronze/readings/minutes/date={captured_at:%Y-%m-%d}/hour={captured_at:%H}/"
        f"{captured_at:%Y-%m-%dT%H-%M-%S.%f}Z.jsonl"
    )
    body = "".join(
        json.dumps(reading, ensure_ascii=False) + "\n" for reading in readings
    )

    s3 = client if client is not None else boto3.client("s3")
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )
    return key
