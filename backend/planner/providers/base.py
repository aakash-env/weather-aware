"""Provider interfaces. Tests use fakes; HTTP clients live in the sibling modules."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from planner.domain.types import LatLon


class ProviderError(Exception):
    """An upstream routing, geocoding, or weather call failed."""


@dataclass(frozen=True)
class RouteOption:
    distance_m: float
    duration_s: float
    geometry: list[LatLon]


@dataclass(frozen=True)
class GeocodeHit:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class HourlySeries:
    times: list[datetime]
    wind_mph: list[float | None]
    rain_in_hr: list[float | None]
    snow_in_hr: list[float | None]


class RoutingProvider(Protocol):
    def get_routes(self, origin: LatLon, destination: LatLon) -> list[RouteOption]:
        """Return up to three real driving routes. Never invent one."""


class GeocodeProvider(Protocol):
    def search(self, query: str, limit: int = 5) -> list[GeocodeHit]:
        """Return autocomplete hits, best first."""


class WeatherProvider(Protocol):
    def fetch(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        """Hourly forecasts keyed by rounded lat/lon. None means that point failed."""
