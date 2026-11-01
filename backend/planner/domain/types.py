"""Shared domain types."""

from dataclasses import dataclass
from typing import Literal

Level = Literal["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "UNKNOWN"]

LEVEL_VALUE: dict[Level, int] = {
    "LOW": 0,
    "MODERATE": 1,
    "HIGH": 2,
    "SEVERE": 3,
    "NO_TRAVEL": 4,
}

LEVEL_LABEL: dict[Level, str] = {
    "LOW": "Low",
    "MODERATE": "Moderate",
    "HIGH": "High",
    "SEVERE": "Severe",
    "NO_TRAVEL": "No Travel",
    "UNKNOWN": "Unknown",
}


def level_value(level: Level) -> int | None:
    """Numeric score used for average risk. Unknown has no score."""
    if level == "UNKNOWN":
        return None
    return LEVEL_VALUE[level]


def max_level(levels: list[Level]) -> Level:
    """Highest known level. Unknown is ignored unless it is the only input."""
    known = [level for level in levels if level != "UNKNOWN"]
    if not known:
        return "UNKNOWN"
    return max(known, key=lambda level: LEVEL_VALUE[level])


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float

    def rounded(self, places: int = 1) -> "LatLon":
        """Round for weather dedupe. 0.1 degree is about 7 miles."""
        return LatLon(round(self.lat, places), round(self.lon, places))
