"""Response formatting shared by the API services."""

from __future__ import annotations

from datetime import UTC, datetime


def iso_utc(value: datetime) -> str:
    """ISO-8601 in UTC with a ``Z`` suffix."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def round_or_none(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
