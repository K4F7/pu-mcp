from __future__ import annotations

from datetime import datetime


def ensure_aware_local(value: datetime) -> datetime:
    """Treat naive datetimes as system-local wall time and return an aware datetime."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.astimezone()
    return value
