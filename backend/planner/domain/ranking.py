"""Route recommendation.

Safe routes are ordered by fewest Severe miles, then fewest High miles, then
fewest unknown miles, then lowest average risk, then shortest duration.
Unknown miles sit after High so missing weather cannot rank as if it were Low.
Blocked routes are disqualified unless every route is blocked, in which case
No Travel miles is the first key. Miles are rounded to 0.1 and average risk to
3 decimals before comparison.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from planner.domain.types import LEVEL_VALUE, Level


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    label: str
    severe_mi: float
    high_mi: float
    moderate_mi: float
    low_mi: float
    no_travel_mi: float
    unknown_mi: float
    avg_risk: float | None
    duration_min: float
    blocked: bool
    max_level: Level


@dataclass(frozen=True)
class RankedRoute:
    route_id: str
    rank: int
    why: str


def metrics_from_segments(
    route_id: str,
    label: str,
    segments: list[tuple[Level, float]],
    duration_min: float,
) -> RouteScore:
    """Sum segment miles by level and compute the mileage-weighted average risk.

    Unknown segments are excluded from the average and from the Low total.
    """
    totals = {
        "LOW": 0.0,
        "MODERATE": 0.0,
        "HIGH": 0.0,
        "SEVERE": 0.0,
        "NO_TRAVEL": 0.0,
        "UNKNOWN": 0.0,
    }
    weighted = 0.0
    scored_miles = 0.0
    for level, miles in segments:
        totals[level] += miles
        value = LEVEL_VALUE.get(level) if level != "UNKNOWN" else None
        if value is not None:
            weighted += miles * value
            scored_miles += miles
    known = [level for level, miles in totals.items() if miles > 0 and level != "UNKNOWN"]
    max_level: Level = max(known, key=lambda level: LEVEL_VALUE[level]) if known else "UNKNOWN"
    return RouteScore(
        route_id=route_id,
        label=label,
        severe_mi=totals["SEVERE"],
        high_mi=totals["HIGH"],
        moderate_mi=totals["MODERATE"],
        low_mi=totals["LOW"],
        no_travel_mi=totals["NO_TRAVEL"],
        unknown_mi=totals["UNKNOWN"],
        avg_risk=None if scored_miles == 0 else weighted / scored_miles,
        duration_min=duration_min,
        blocked=totals["NO_TRAVEL"] > 0,
        max_level=max_level,
    )


def rank_routes(routes: list[RouteScore]) -> list[RankedRoute]:
    """Return every route, best first, with a short explanation."""
    if not routes:
        return []
    all_blocked = all(route.blocked for route in routes)
    if all_blocked:
        ordered = sorted(routes, key=_blocked_key)
        fastest = min(route.duration_min for route in routes)
    else:
        safe = sorted((route for route in routes if not route.blocked), key=_safe_key)
        blocked = sorted((route for route in routes if route.blocked), key=_blocked_key)
        ordered = safe + blocked
        fastest = min(route.duration_min for route in safe)
    return [
        RankedRoute(
            route_id=route.route_id,
            rank=index + 1,
            why=_why(route, ordered, fastest, all_blocked),
        )
        for index, route in enumerate(ordered)
    ]


def round_miles(value: float) -> float:
    """Round miles half-up to one decimal so ranking does not depend on binary dust."""
    return _round_half_up(value, 1)


def round_risk(value: float) -> float:
    """Round average risk half-up to three decimals."""
    return _round_half_up(value, 3)


def _safe_key(route: RouteScore) -> tuple[float, float, float, float, float]:
    return (
        round_miles(route.severe_mi),
        round_miles(route.high_mi),
        round_miles(route.unknown_mi),
        999.0 if route.avg_risk is None else round_risk(route.avg_risk),
        route.duration_min,
    )


def _blocked_key(route: RouteScore) -> tuple[float, ...]:
    return (round_miles(route.no_travel_mi), *_safe_key(route))


def _why(
    route: RouteScore,
    ordered: list[RouteScore],
    fastest_min: float,
    all_blocked: bool,
) -> str:
    others = [item for item in ordered if item.route_id != route.route_id]
    if route.blocked and not all_blocked:
        return (
            f"Blocked: {_fmt_mi(route.no_travel_mi)} No Travel miles. "
            "Disqualified from the recommendation."
        )
    if all_blocked:
        rival = _extreme(route, others, "no_travel_mi")
        if rival is None:
            return "No safe route."
        return (
            f"No safe route. {_fmt_mi(route.no_travel_mi)} No Travel miles vs "
            f"{_fmt_mi(rival.no_travel_mi)} on {rival.label}."
        )
    contrast = _contrast(route, others)
    delta = route.duration_min - fastest_min
    if delta <= 0.5:
        time_text = "shortest travel time"
    else:
        time_text = f"+{int(round(delta))} min vs fastest"
    if contrast:
        return f"{contrast}; {time_text}."
    return f"{time_text[0].upper()}{time_text[1:]}."


def _contrast(route: RouteScore, others: list[RouteScore]) -> str:
    if not others:
        return ""
    for attr, label in (
        ("severe_mi", "Severe"),
        ("high_mi", "High"),
        ("unknown_mi", "unknown"),
    ):
        mine = round_miles(getattr(route, attr))
        rival = max(others, key=lambda item: round_miles(getattr(item, attr)))
        theirs = round_miles(getattr(rival, attr))
        if mine != theirs:
            return f"{_fmt_mi(mine)} {label} miles vs {_fmt_mi(theirs)} on {rival.label}"
    mine_avg = None if route.avg_risk is None else round_risk(route.avg_risk)
    rival = max(
        others,
        key=lambda item: -1.0 if item.avg_risk is None else round_risk(item.avg_risk),
    )
    their_avg = None if rival.avg_risk is None else round_risk(rival.avg_risk)
    if mine_avg != their_avg:
        left = "unavailable" if mine_avg is None else f"{mine_avg:.3f}"
        right = "unavailable" if their_avg is None else f"{their_avg:.3f}"
        return f"average risk {left} vs {right} on {rival.label}"
    return f"Same risk as {others[0].label}"


def _extreme(route: RouteScore, others: list[RouteScore], attr: str) -> RouteScore | None:
    if not others:
        return None
    return max(others, key=lambda item: round_miles(getattr(item, attr)))


def _fmt_mi(value: float) -> str:
    rounded = round_miles(value)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.1f}"


def _round_half_up(value: float, places: int) -> float:
    quant = Decimal("1").scaleb(-places)
    decimal_value = Decimal(str(value))
    return float(decimal_value.quantize(quant, rounding=ROUND_HALF_UP))
