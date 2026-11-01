"""Open-Meteo hourly forecasts. Coordinates are batched and fetched in parallel."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx

from planner.domain.types import LatLon
from planner.providers.base import HourlySeries, ProviderError
from planner.providers.http import request_json

BATCH_SIZE = 50
MAX_WORKERS = 4
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoWeather:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache=None,
        ttl_seconds: int = 1800,
    ):
        self._client = client
        self._cache = cache
        self._ttl = ttl_seconds

    def fetch(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        unique: list[LatLon] = []
        seen: set[tuple[float, float]] = set()
        for point in points:
            rounded = point.rounded()
            key = (rounded.lat, rounded.lon)
            if key not in seen:
                seen.add(key)
                unique.append(rounded)

        found: dict[tuple[float, float], HourlySeries | None] = {}
        missing: list[LatLon] = []
        for point in unique:
            cached = self._read_cache(point, forecast_days)
            if cached is None and not self._cache_has(point, forecast_days):
                missing.append(point)
            else:
                found[(point.lat, point.lon)] = cached
        if not missing:
            return found

        fetched = self._fetch_all(missing, forecast_days)
        for point in missing:
            key = (point.lat, point.lon)
            series = fetched.get(key)
            found[key] = series
            if series is not None:
                self._write_cache(point, forecast_days, series)
        return found

    def _fetch_all(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        chunks = [points[index : index + BATCH_SIZE] for index in range(0, len(points), BATCH_SIZE)]
        merged: dict[tuple[float, float], HourlySeries | None] = {}
        workers = min(MAX_WORKERS, len(chunks)) or 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self._fetch_chunk, chunk, forecast_days) for chunk in chunks]
            for chunk, future in zip(chunks, futures, strict=True):
                try:
                    merged.update(future.result())
                except ProviderError:
                    for point in chunk:
                        merged[(point.lat, point.lon)] = None
        return merged

    def _fetch_chunk(
        self,
        points: list[LatLon],
        forecast_days: int,
    ) -> dict[tuple[float, float], HourlySeries | None]:
        params = {
            "latitude": ",".join(f"{point.lat:.1f}" for point in points),
            "longitude": ",".join(f"{point.lon:.1f}" for point in points),
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "forecast_days": forecast_days,
        }
        client = self._client or httpx.Client()
        close = self._client is None
        try:
            payload = request_json(client, FORECAST_URL, params, timeout=45)
        finally:
            if close:
                client.close()
        rows = payload if isinstance(payload, list) else [payload]
        if len(rows) != len(points):
            raise ProviderError(
                "Open-Meteo returned a different number of locations than requested."
            )
        parsed: dict[tuple[float, float], HourlySeries | None] = {}
        for point, row in zip(points, rows, strict=True):
            parsed[(point.lat, point.lon)] = _parse_row(row) if isinstance(row, dict) else None
        return parsed

    def _cache_key(self, point: LatLon, forecast_days: int) -> str:
        return f"wx:v1:{point.lat:.1f}:{point.lon:.1f}:{forecast_days}"

    def _cache_has(self, point: LatLon, forecast_days: int) -> bool:
        if self._cache is None:
            return False
        return self._cache.get(self._cache_key(point, forecast_days)) is not None

    def _read_cache(self, point: LatLon, forecast_days: int) -> HourlySeries | None:
        if self._cache is None:
            return None
        return self._cache.get(self._cache_key(point, forecast_days))

    def _write_cache(self, point: LatLon, forecast_days: int, series: HourlySeries) -> None:
        if self._cache is None:
            return
        self._cache.set(self._cache_key(point, forecast_days), series, self._ttl)


def _parse_row(row: dict) -> HourlySeries | None:
    hourly = row.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times = []
    for stamp in hourly.get("time") or []:
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        times.append(parsed)
    if not times:
        return None
    rain = [_number(value) for value in _column(hourly, "rain", len(times))]
    showers = [_number(value) for value in _column(hourly, "showers", len(times))]
    return HourlySeries(
        times=times,
        wind_mph=[_number(value) for value in _column(hourly, "wind_speed_10m", len(times))],
        rain_in_hr=[_sum_pair(left, right) for left, right in zip(rain, showers, strict=True)],
        snow_in_hr=[_number(value) for value in _column(hourly, "snowfall", len(times))],
    )


def _column(hourly: dict, name: str, size: int) -> list:
    values = list(hourly.get(name) or [])
    if len(values) < size:
        values.extend([None] * (size - len(values)))
    return values[:size]


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_pair(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return (left or 0.0) + (right or 0.0)
