"""Bronze : archivage S3 des mesures telles que reçues de l'API énergie."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from typing import Any

import boto3


# Une mesure par ligne (JSON Lines), sans modification des champs reçus.
# Clé partitionnée par date et heure UTC de la minute mesurée :
#   bronze/readings/minutes/date=2026-10-21/hour=08/2026-10-21T08-08Z.jsonl
# Rejouer la même minute écrase le même objet (pas de doublon).
# Sans BRONZE_BUCKET (poste local), rien n'est écrit et None est retourné.
def write_readings_bronze(
    readings: Sequence[Mapping[str, Any]],
    bucket: str | None = None,
    *,
    client: Any = None,
) -> str | None:
    bucket_name = (
        bucket if bucket is not None else os.environ.get("BRONZE_BUCKET", "")
    ).strip()
    if not bucket_name or not readings:
        return None

    timestamps = {reading["timestamp"] for reading in readings}
    if len(timestamps) != 1:
        raise ValueError("Les mesures d'un lot bronze doivent porter le même timestamp.")
    minute = datetime.fromisoformat(timestamps.pop()).astimezone(timezone.utc)

    key = (
        f"bronze/readings/minutes/date={minute:%Y-%m-%d}/hour={minute:%H}/"
        f"{minute:%Y-%m-%dT%H-%M}Z.jsonl"
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
