import pytest

from planner.domain.risk import (
    classify_conditions,
    classify_rain,
    classify_snow,
    classify_wind_speed,
    wind_level_with_load,
)

WIND_EDGES = [
    (0, "LOW"),
    (24.99, "LOW"),
    (25.0, "MODERATE"),
    (34.99, "MODERATE"),
    (35.0, "HIGH"),
    (44.9, "HIGH"),
    (44.99, "HIGH"),
    (45.0, "SEVERE"),
    (54.9, "SEVERE"),
    (54.99, "SEVERE"),
    (55.0, "NO_TRAVEL"),
    (70, "NO_TRAVEL"),
]

RAIN_EDGES = [
    (0, "LOW"),
    (0.099, "LOW"),
    (0.10, "MODERATE"),
    (0.249, "MODERATE"),
    (0.25, "HIGH"),
    (0.499, "HIGH"),
    (0.50, "SEVERE"),
    (1.00, "SEVERE"),
    (1.01, "NO_TRAVEL"),
    (2.0, "NO_TRAVEL"),
]

SNOW_EDGES = [
    (0, "LOW"),
    (0.49, "LOW"),
    (0.5, "MODERATE"),
    (0.99, "MODERATE"),
    (1.0, "HIGH"),
    (1.99, "HIGH"),
    (2.0, "SEVERE"),
    (3.0, "SEVERE"),
    (3.01, "NO_TRAVEL"),
    (4, "NO_TRAVEL"),
]


@pytest.mark.parametrize("mph,level", WIND_EDGES)
def test_wind_edges(mph, level):
    assert classify_wind_speed(mph) == level


@pytest.mark.parametrize("rate,level", RAIN_EDGES)
def test_rain_edges(rate, level):
    assert classify_rain(rate) == level


@pytest.mark.parametrize("rate,level", SNOW_EDGES)
def test_snow_edges(rate, level):
    assert classify_snow(rate) == level


@pytest.mark.parametrize(
    "mph,load,expected",
    [
        (55, 1, "NO_TRAVEL"),
        (55, 80_000, "NO_TRAVEL"),
        (54.9, 30_000, "SEVERE"),
        (54.9, 30_001, "NO_TRAVEL"),
        (45, 30_000, "SEVERE"),
        (45, 30_001, "NO_TRAVEL"),
        (44.9, 40_000, "HIGH"),
        (44.9, 40_001, "SEVERE"),
        (35, 40_000, "HIGH"),
        (35, 40_001, "SEVERE"),
        (34.99, 80_000, "MODERATE"),
        (25, 80_000, "MODERATE"),
        (10, 80_000, "LOW"),
    ],
)
def test_load_rules_only_raise(mph, load, expected):
    _base, adjusted = wind_level_with_load(mph, load)
    assert adjusted == expected


def test_checkpoint_takes_the_worst_factor():
    result = classify_conditions(
        wind_mph=10,
        rain_in_hr=0.4,
        snow_in_hr=0.1,
        load_lbs=10_000,
    )
    assert result.level == "HIGH"
    assert result.levels.wind == "LOW"
    assert result.levels.rain == "HIGH"
    assert result.levels.snow == "LOW"
    assert result.reasons == ["Rain 0.40 in/hr → High"]
    assert result.status == "ok"


def test_load_override_reason():
    result = classify_conditions(
        wind_mph=47,
        rain_in_hr=0,
        snow_in_hr=0,
        load_lbs=34_000,
    )
    assert result.level == "NO_TRAVEL"
    assert result.levels.wind == "NO_TRAVEL"
    assert result.reasons == ["Wind 47 mph + load 34,000 lb → No Travel"]


def test_exact_weight_does_not_override():
    result = classify_conditions(
        wind_mph=47,
        rain_in_hr=0,
        snow_in_hr=0,
        load_lbs=30_000,
    )
    assert result.level == "SEVERE"
    assert result.reasons == ["Wind 47 mph → Severe"]


def test_missing_weather_is_unknown_not_low():
    result = classify_conditions(
        wind_mph=None,
        rain_in_hr=0,
        snow_in_hr=0,
        load_lbs=10_000,
    )
    assert result.level == "UNKNOWN"
    assert result.status == "unknown"
    assert result.reasons == ["Forecast unavailable"]
    assert "LOW" not in (result.levels.wind, result.levels.rain, result.levels.snow)


def test_partial_missing_field_is_unknown():
    result = classify_conditions(
        wind_mph=10,
        rain_in_hr=None,
        snow_in_hr=0,
        load_lbs=10_000,
    )
    assert result.status == "unknown"
    assert result.level == "UNKNOWN"


def test_beyond_forecast_keeps_the_clamped_level_and_says_so():
    result = classify_conditions(
        wind_mph=12,
        rain_in_hr=0,
        snow_in_hr=0,
        load_lbs=10_000,
        beyond_forecast=True,
    )
    assert result.level == "LOW"
    assert result.status == "beyond_forecast"
    assert result.reasons == [
        "ETA is outside the forecast window; values are from the nearest available hour."
    ]


def test_snow_can_outweigh_a_calm_wind():
    result = classify_conditions(
        wind_mph=5,
        rain_in_hr=0,
        snow_in_hr=3.01,
        load_lbs=10_000,
    )
    assert result.level == "NO_TRAVEL"
    assert result.levels.snow == "NO_TRAVEL"
