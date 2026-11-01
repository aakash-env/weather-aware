import pytest

from planner.domain.ranking import RouteScore, metrics_from_segments, rank_routes, round_miles


def score(
    route_id: str,
    label: str,
    *,
    severe: float = 0,
    high: float = 0,
    moderate: float = 0,
    low: float = 100,
    no_travel: float = 0,
    unknown: float = 0,
    avg: float | None = 0,
    duration: float = 100,
    blocked: bool | None = None,
    max_level: str = "LOW",
) -> RouteScore:
    return RouteScore(
        route_id=route_id,
        label=label,
        severe_mi=severe,
        high_mi=high,
        moderate_mi=moderate,
        low_mi=low,
        no_travel_mi=no_travel,
        unknown_mi=unknown,
        avg_risk=avg,
        duration_min=duration,
        blocked=no_travel > 0 if blocked is None else blocked,
        max_level=max_level,  # type: ignore[arg-type]
    )


def test_lexicographic_order_and_why_text():
    routes = [
        score("r1", "Route 1", severe=42, avg=1.2, duration=900, max_level="SEVERE"),
        score("r2", "Route 2", severe=0, high=10, avg=0.4, duration=938, max_level="HIGH"),
        score("r3", "Route 3", severe=0, high=40, avg=0.2, duration=910, max_level="HIGH"),
    ]
    ranked = rank_routes(routes)
    assert [item.route_id for item in ranked] == ["r2", "r3", "r1"]
    assert ranked[0].why == "0 Severe miles vs 42 on Route 1; +38 min vs fastest."
    assert ranked[2].rank == 3


def test_high_miles_break_a_severe_tie():
    routes = [
        score("r1", "Route 1", severe=0, high=40, duration=100),
        score("r2", "Route 2", severe=0, high=10, duration=140),
    ]
    ranked = rank_routes(routes)
    assert ranked[0].route_id == "r2"
    assert "High miles" in ranked[0].why
    assert "+40 min vs fastest" in ranked[0].why


def test_average_risk_then_duration():
    routes = [
        score("r1", "Route 1", avg=0.5, duration=80),
        score("r2", "Route 2", avg=0.2, duration=120),
        score("r3", "Route 3", avg=0.2, duration=90),
    ]
    ranked = rank_routes(routes)
    assert [item.route_id for item in ranked] == ["r3", "r2", "r1"]
    assert ranked[0].why == "average risk 0.200 vs 0.500 on Route 1; +10 min vs fastest."
    assert "shortest travel time" in ranked[2].why


def test_blocked_routes_are_disqualified_but_still_ranked():
    routes = [
        score("r1", "Route 1", no_travel=20, severe=0, duration=50, max_level="NO_TRAVEL"),
        score("r2", "Route 2", severe=5, duration=200, max_level="SEVERE"),
        score("r3", "Route 3", no_travel=5, duration=80, max_level="NO_TRAVEL"),
    ]
    ranked = rank_routes(routes)
    assert [item.route_id for item in ranked] == ["r2", "r3", "r1"]
    assert ranked[1].why.startswith("Blocked:")
    assert ranked[0].route_id == "r2"


def test_all_blocked_ranks_by_no_travel_miles():
    routes = [
        score("r1", "Route 1", no_travel=80, severe=0, duration=100),
        score("r2", "Route 2", no_travel=20, severe=40, duration=300),
    ]
    ranked = rank_routes(routes)
    assert [item.route_id for item in ranked] == ["r2", "r1"]
    assert ranked[0].why == "No safe route. 20 No Travel miles vs 80 on Route 1."


def test_rounding_ignores_float_dust():
    assert round_miles(10.04) == 10.0
    assert round_miles(10.05) == 10.1
    routes = [
        score("r1", "Route 1", severe=10.04, duration=50),
        score("r2", "Route 2", severe=10.06, duration=40),
    ]
    ranked = rank_routes(routes)
    assert ranked[0].route_id == "r1"


def test_unknown_miles_do_not_count_as_low_and_sort_after_high():
    metrics = metrics_from_segments(
        "r1",
        "Route 1",
        [("LOW", 10), ("UNKNOWN", 5), ("HIGH", 5)],
        duration_min=60,
    )
    assert metrics.low_mi == 10
    assert metrics.unknown_mi == 5
    assert metrics.avg_risk == pytest.approx(10 / 15)
    assert metrics.blocked is False
    assert metrics.max_level == "HIGH"

    fully_known = score("r2", "Route 2", high=5, low=15, avg=0.5, duration=70)
    unknown_route = metrics
    ranked = rank_routes([unknown_route, fully_known])
    assert [item.route_id for item in ranked] == ["r2", "r1"]


def test_all_unknown_has_no_average_and_is_not_low():
    metrics = metrics_from_segments("r1", "Route 1", [("UNKNOWN", 12)], duration_min=30)
    assert metrics.avg_risk is None
    assert metrics.low_mi == 0
    assert metrics.max_level == "UNKNOWN"
    assert metrics.blocked is False


def test_segment_metrics_mark_blocked():
    metrics = metrics_from_segments(
        "r1",
        "Route 1",
        [("LOW", 8), ("NO_TRAVEL", 2)],
        duration_min=40,
    )
    assert metrics.blocked is True
    assert metrics.max_level == "NO_TRAVEL"
    assert metrics.avg_risk == 0.8
