from datetime import UTC, datetime


def parse_reading_timestamp(value: str | datetime) -> datetime:
    try:
        timestamp = (
            value if isinstance(value, datetime) else datetime.fromisoformat(value)
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Timestamp de mesure invalide.") from error
    if timestamp.utcoffset() is None:
        # /current uses UTC without a suffix; checked with the HTTP Date header.
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
