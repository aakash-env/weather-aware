"""Weather and load risk classification."""

from dataclasses import dataclass

from planner.domain.types import LEVEL_LABEL, Level, max_level


@dataclass(frozen=True)
class FactorLevels:
    wind: Level
    rain: Level
    snow: Level


@dataclass(frozen=True)
class Classification:
    level: Level
    levels: FactorLevels
    reasons: list[str]
    status: str


def classify_wind_speed(mph: float) -> Level:
    """Map sustained wind to a level.

    Moderate, High, and Severe start at their lower bound (inclusive).
    No Travel starts at 55 mph. 44.9 is High and 54.9 is Severe.
    """
    if mph >= 55:
        return "NO_TRAVEL"
    if mph >= 45:
        return "SEVERE"
    if mph >= 35:
        return "HIGH"
    if mph >= 25:
        return "MODERATE"
    return "LOW"


def classify_rain(inches_per_hour: float) -> Level:
    """Map rain rate to a level. Exactly 1.00 in/hr is Severe; above that is No Travel."""
    if inches_per_hour > 1.00:
        return "NO_TRAVEL"
    if inches_per_hour >= 0.50:
        return "SEVERE"
    if inches_per_hour >= 0.25:
        return "HIGH"
    if inches_per_hour >= 0.10:
        return "MODERATE"
    return "LOW"


def classify_snow(inches_per_hour: float) -> Level:
    """Map snowfall depth to a level. Exactly 3.0 in/hr is Severe; above that is No Travel."""
    if inches_per_hour > 3.0:
        return "NO_TRAVEL"
    if inches_per_hour >= 2.0:
        return "SEVERE"
    if inches_per_hour >= 1.0:
        return "HIGH"
    if inches_per_hour >= 0.5:
        return "MODERATE"
    return "LOW"


def wind_level_with_load(mph: float, load_lbs: float) -> tuple[Level, Level]:
    """Return the base wind level and the level after load rules.

    Load rules only raise the result. Weight comparisons are strict:
    exactly 30,000 lb or 40,000 lb does not trigger an override.
    """
    base = classify_wind_speed(mph)
    override: Level = base
    if mph >= 55:
        override = "NO_TRAVEL"
    elif 45 <= mph < 55 and load_lbs > 30_000:
        override = "NO_TRAVEL"
    elif 35 <= mph < 45 and load_lbs > 40_000:
        override = "SEVERE"
    return base, max_level([base, override])


def classify_conditions(
    *,
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_lbs: float,
    beyond_forecast: bool = False,
) -> Classification:
    """Classify one checkpoint.

    The checkpoint level is the worst of wind (after load rules), rain, and snow.
    Missing weather is Unknown and is never reported as Low.
    """
    if wind_mph is None or rain_in_hr is None or snow_in_hr is None:
        return Classification(
            level="UNKNOWN",
            levels=FactorLevels("UNKNOWN", "UNKNOWN", "UNKNOWN"),
            reasons=["Forecast unavailable"],
            status="unknown",
        )

    base_wind, wind = wind_level_with_load(wind_mph, load_lbs)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    reasons: list[str] = []
    if wind != "LOW":
        if wind != base_wind:
            reasons.append(
                f"Wind {_fmt(wind_mph, 1)} mph + load {_fmt(load_lbs, 0)} lb → {LEVEL_LABEL[wind]}"
            )
        else:
            reasons.append(f"Wind {_fmt(wind_mph, 1)} mph → {LEVEL_LABEL[wind]}")
    if rain != "LOW":
        reasons.append(f"Rain {_fmt(rain_in_hr, 2)} in/hr → {LEVEL_LABEL[rain]}")
    if snow != "LOW":
        reasons.append(f"Snow {_fmt(snow_in_hr, 1)} in/hr → {LEVEL_LABEL[snow]}")
    if beyond_forecast:
        reasons.append(
            "ETA is outside the forecast window; values are from the nearest available hour."
        )
    return Classification(
        level=max_level([wind, rain, snow]),
        levels=FactorLevels(wind, rain, snow),
        reasons=reasons,
        status="beyond_forecast" if beyond_forecast else "ok",
    )


def _fmt(value: float, digits: int) -> str:
    rounded = round(value, digits)
    if abs(rounded - round(rounded)) < 10 ** (-digits):
        return f"{int(round(rounded)):,}"
    return f"{rounded:,.{digits}f}"
