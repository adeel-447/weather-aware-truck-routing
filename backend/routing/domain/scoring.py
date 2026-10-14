"""Per-route mileage accounting by severity."""

from __future__ import annotations

from collections.abc import Sequence

from routing.domain.types import Checkpoint, Severity, SeveritySummary


def summarize(checkpoints: Sequence[Checkpoint], total_miles: float) -> SeveritySummary:
    """Sum each checkpoint's representative interval into its severity bucket.

    Weighted average risk = sum(miles x severity value) / known miles (Low=0 ... No Travel=4).
    Unknown-severity miles are excluded from the average and reported separately.
    """
    miles = dict.fromkeys(Severity, 0.0)
    unknown = 0.0
    for checkpoint in checkpoints:
        severity = checkpoint.risk.severity
        if severity is None:
            unknown += checkpoint.interval_miles
        else:
            miles[severity] += checkpoint.interval_miles
    known = sum(miles.values())
    weighted = sum(m * s.value for s, m in miles.items()) / known if known > 0 else None
    return SeveritySummary(
        miles=miles, unknown_miles=unknown, total_miles=total_miles, weighted_average_risk=weighted
    )
