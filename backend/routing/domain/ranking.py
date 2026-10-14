"""Route recommendation.

Policy (CLAUDE.md): routes with any No Travel miles are ineligible; routes with unknown-weather miles are
unverified and cannot be recommended. Remaining routes are ordered lexicographically by
(Severe miles, High miles, weighted average risk, duration, route id). No weighted score is used.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from routing.domain.types import Severity, SeveritySummary

# Mile totals are compared at 0.01 mi and averages at 1e-6 so float noise cannot flip a tie.
MILES_PRECISION = 2
AVERAGE_PRECISION = 6


class RecommendationStatus(StrEnum):
    RECOMMENDED = "recommended"
    NO_SAFE_ROUTE = "no_safe_route"
    INSUFFICIENT_DATA = "insufficient_data"


class RouteStanding(StrEnum):
    RECOMMENDED = "recommended"
    ELIGIBLE = "eligible"
    UNVERIFIED = "unverified"
    NO_TRAVEL = "no_travel"


@dataclass(frozen=True, slots=True)
class RouteScore:
    route_id: str
    duration_seconds: float
    summary: SeveritySummary


@dataclass(frozen=True, slots=True)
class RankedRoute:
    route_id: str
    rank: int
    standing: RouteStanding
    note: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    status: RecommendationStatus
    recommended_route_id: str | None
    reason: str
    ranked: tuple[RankedRoute, ...]


def _miles(summary: SeveritySummary, severity: Severity) -> float:
    return round(summary.miles[severity], MILES_PRECISION)


def sort_key(score: RouteScore) -> tuple[float, float, float, float, str]:
    average = score.summary.weighted_average_risk
    return (
        _miles(score.summary, Severity.SEVERE),
        _miles(score.summary, Severity.HIGH),
        round(average, AVERAGE_PRECISION) if average is not None else float("inf"),
        score.duration_seconds,
        score.route_id,
    )


def _fmt(miles: float) -> str:
    return f"{miles:.1f} mi"


def _hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f} h"


def _standing(score: RouteScore) -> RouteStanding:
    if score.summary.has_no_travel:
        return RouteStanding.NO_TRAVEL
    if not score.summary.is_verified:
        return RouteStanding.UNVERIFIED
    return RouteStanding.ELIGIBLE


def _exclusion_note(score: RouteScore, standing: RouteStanding) -> str:
    if standing == RouteStanding.NO_TRAVEL:
        return f"Not eligible: {_fmt(score.summary.miles[Severity.NO_TRAVEL])} of No Travel conditions."
    return f"Unverified: forecast unavailable for {_fmt(score.summary.unknown_miles)}."


def _deciding_reason(winner: RouteScore, runner_up: RouteScore) -> str:
    w, r = sort_key(winner), sort_key(runner_up)
    if w[0] != r[0]:
        return f"fewest Severe miles ({_fmt(w[0])} vs {_fmt(r[0])} on route {runner_up.route_id})"
    if w[1] != r[1]:
        return (
            f"equal Severe miles; fewest High miles ({_fmt(w[1])} vs {_fmt(r[1])} on route "
            f"{runner_up.route_id})"
        )
    if w[2] != r[2]:
        return (
            f"equal Severe and High miles; lowest average risk ({w[2]:.2f} vs {r[2]:.2f} on route "
            f"{runner_up.route_id})"
        )
    if w[3] != r[3]:
        return (
            f"equal weather risk; shortest travel time ({_hours(w[3])} vs {_hours(r[3])} on route "
            f"{runner_up.route_id})"
        )
    return f"identical on all criteria to route {runner_up.route_id}; chosen by route ID"


def recommend(scores: Sequence[RouteScore]) -> Recommendation:
    if not scores:
        raise ValueError("no routes to rank")
    if len({s.route_id for s in scores}) != len(scores):
        raise ValueError("route ids must be unique")

    standings = {s.route_id: _standing(s) for s in scores}
    group_order = {RouteStanding.ELIGIBLE: 0, RouteStanding.UNVERIFIED: 1, RouteStanding.NO_TRAVEL: 2}

    def display_key(score: RouteScore) -> tuple[int, float, tuple[float, float, float, float, str]]:
        no_travel = _miles(score.summary, Severity.NO_TRAVEL)
        return (group_order[standings[score.route_id]], no_travel, sort_key(score))

    ordered = sorted(scores, key=display_key)
    eligible = [s for s in ordered if standings[s.route_id] == RouteStanding.ELIGIBLE]

    if eligible:
        winner = eligible[0]
        status = RecommendationStatus.RECOMMENDED
        if len(eligible) > 1:
            reason = f"Route {winner.route_id} recommended: {_deciding_reason(winner, eligible[1])}."
        else:
            reason = (
                f"Route {winner.route_id} recommended: the only route with complete forecast coverage "
                f"and no No Travel conditions."
            )
    elif any(standing == RouteStanding.UNVERIFIED for standing in standings.values()):
        winner = None
        status = RecommendationStatus.INSUFFICIENT_DATA
        reason = (
            "No route can be recommended: every route without No Travel conditions is missing forecast "
            "data for part of the trip."
        )
    else:
        winner = None
        status = RecommendationStatus.NO_SAFE_ROUTE
        reason = "No safe route: every route has No Travel conditions at the estimated arrival times."

    ranked = []
    for rank, score in enumerate(ordered, start=1):
        standing = standings[score.route_id]
        if winner is not None and score.route_id == winner.route_id:
            ranked.append(RankedRoute(score.route_id, rank, RouteStanding.RECOMMENDED, reason))
        elif standing == RouteStanding.ELIGIBLE:
            ranked.append(
                RankedRoute(score.route_id, rank, standing, "Eligible; ranked lower on the criteria.")
            )
        else:
            ranked.append(RankedRoute(score.route_id, rank, standing, _exclusion_note(score, standing)))

    return Recommendation(
        status=status,
        recommended_route_id=winner.route_id if winner else None,
        reason=reason,
        ranked=tuple(ranked),
    )
