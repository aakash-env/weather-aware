"""Turn a trip request into routes, risk, a recommendation, and a heatmap."""

from datetime import UTC, datetime, timedelta

from planner.domain.forecast import forecast_days_for, nearest_hour
from planner.domain.geo import (
    METERS_PER_MILE,
    cumulative_miles,
    encode_polyline6,
    haversine_mi,
    point_at_mile,
    simplify,
)
from planner.domain.ranking import metrics_from_segments, rank_routes, round_miles, round_risk
from planner.domain.risk import classify_conditions
from planner.domain.sampling import checkpoint_miles, segment_miles
from planner.domain.types import LEVEL_VALUE, LatLon
from planner.providers.base import HourlySeries, ProviderError, RouteOption

ASSUMPTIONS = [
    (
        "Checkpoint interval (10/25/50 mi) is a user-selectable sampling interval. "
        "The default is 25."
    ),
    (
        "Risk per checkpoint is the worst of wind, rain, and snow after load rules. "
        "Wind is sustained 10 m speed, not gusts."
    ),
    (
        "Moderate, High, and Severe lower bounds are inclusive. "
        "Wind No Travel is >= 55 mph. Rain No Travel is > 1.00 in/hr. "
        "Snow No Travel is > 3.0 in/hr."
    ),
    (
        "ETA is proportional to distance along the route using the routing API's total duration. "
        "Durations are car-based; there is no HGV speed adjustment."
    ),
    (
        "The forecast hour is the nearest whole UTC hour to the ETA. "
        "Open-Meteo hourly precipitation is the total for that hour, treated as in/hr. "
        "Snow is snowfall depth in/hr."
    ),
    (
        "Heatmap hour h is the weather at departure + h along the corridor, "
        "independent of where the truck is."
    ),
    (
        "Ranking is lexicographic: fewest Severe miles, then fewest High miles, "
        "then lowest average risk, then shortest travel time. "
        "Blocked routes are disqualified unless every route is blocked."
    ),
    "Units are US-focused: mph, pounds, and inches.",
    (
        "Rain is Open-Meteo rain plus showers. "
        "Coordinates are rounded to 0.1 degree before the forecast lookup. "
        "Unknown miles are left out of average risk and are not counted as Low."
    ),
    (
        "Open-Meteo forecast_days runs from today (UTC), not from departure. "
        "The request covers departure + 72h and is capped at 16 days. "
        "Heatmap hours outside that window are unknown (-1), not Low."
    ),
]

HEATMAP_INTERVAL_MI = 25
SIMPLIFY_TOLERANCE_M = 150


class PlanningError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class TripPlanner:
    def __init__(self, routing, geocoder, weather, routing_source: str, clock=None):
        self.routing = routing
        self.geocoder = geocoder
        self.weather = weather
        self.routing_source = routing_source
        self._clock = clock or (lambda: datetime.now(UTC))

    def plan(self, payload: dict) -> dict:
        now = self._clock()
        origin = self._resolve(payload["origin"], "origin")
        destination = self._resolve(payload["destination"], "destination")
        if haversine_mi(origin[0], destination[0]) < 0.2:
            raise PlanningError("Origin and destination are the same place.", 400)

        departure: datetime = payload["departure"]
        warnings: list[str] = []
        if departure < now - timedelta(minutes=1):
            warnings.append("Departure is in the past. The forecast may no longer match this trip.")
        if departure > now + timedelta(days=16):
            raise PlanningError(
                "Departure is more than 16 days ahead, which is outside the forecast.",
                400,
            )

        try:
            options = self.routing.get_routes(origin[0], destination[0])
        except ProviderError as exc:
            raise PlanningError(str(exc), 502) from exc
        if not options:
            raise PlanningError("No driving route was found for that pair of places.", 502)

        prepared = [_prepare(option, index) for index, option in enumerate(options[:3])]
        prepared = [route for route in prepared if route is not None]
        if not prepared:
            raise PlanningError("Routing geometry could not be read.", 502)

        load_lbs = payload["load_lbs"]
        interval = payload["interval_mi"]
        days = forecast_days_for(now, departure)
        weather_points = _weather_points(prepared, interval)
        try:
            forecasts = self.weather.fetch(weather_points, days)
        except ProviderError:
            forecasts = {}

        routes = [
            _build_route(route, interval, departure, load_lbs, forecasts) for route in prepared
        ]
        scores = [route.pop("_score") for route in routes]
        ranking = rank_routes(scores)
        recommended = ranking[0].route_id if ranking else None
        notices = []
        if len(routes) < 3:
            notices.append(
                f"The routing provider returned {len(routes)} route"
                f"{'' if len(routes) == 1 else 's'}, not 3. Only real routes are shown."
            )
        if scores and all(score.blocked for score in scores):
            warnings.append("No safe route. Every option includes No Travel conditions.")

        return {
            "routes": routes,
            "recommended_route_id": recommended,
            "ranking": [
                {"route_id": item.route_id, "rank": item.rank, "why": item.why} for item in ranking
            ],
            "heatmap": _heatmap(prepared, departure, load_lbs, forecasts),
            "meta": {
                "assumptions": ASSUMPTIONS,
                "weather_source": "open-meteo",
                "routing_source": self.routing_source,
                "generated_at": now.isoformat(),
                "notices": notices,
                "warnings": warnings,
                "origin": {"lat": origin[0].lat, "lon": origin[0].lon, "label": origin[1]},
                "destination": {
                    "lat": destination[0].lat,
                    "lon": destination[0].lon,
                    "label": destination[1],
                },
            },
        }

    def _resolve(self, place: dict, name: str) -> tuple[LatLon, str]:
        if "lat" in place:
            label = place.get("label") or f"{place['lat']:.4f}, {place['lon']:.4f}"
            return LatLon(float(place["lat"]), float(place["lon"])), label
        query = place.get("query", "")
        try:
            hits = self.geocoder.search(query, limit=1)
        except ProviderError as exc:
            raise PlanningError(f"Could not geocode {name}: {exc}", 502) from exc
        if not hits:
            raise PlanningError(f"No geocoding match for {name} ({query}).", 400)
        hit = hits[0]
        return LatLon(hit.lat, hit.lon), hit.label


def _prepare(option: RouteOption, index: int) -> dict | None:
    simplified = simplify(option.geometry, SIMPLIFY_TOLERANCE_M)
    if len(simplified) < 2:
        simplified = option.geometry
    if len(simplified) < 2:
        return None
    cumulative = cumulative_miles(simplified)
    api_miles = option.distance_m / METERS_PER_MILE
    if api_miles <= 0:
        api_miles = cumulative[-1]
    return {
        "id": f"r{index + 1}",
        "label": f"Route {index + 1}",
        "geometry": simplified,
        "cumulative": cumulative,
        "distance_mi": api_miles,
        "duration_min": int(round(option.duration_s / 60)),
        "duration_s": option.duration_s,
    }


def _along(route: dict, mile: float) -> LatLon:
    geometry_miles = route["cumulative"][-1]
    distance = route["distance_mi"]
    if geometry_miles <= 0 or distance <= 0:
        return route["geometry"][0]
    fraction_mile = mile / distance * geometry_miles
    return point_at_mile(route["geometry"], route["cumulative"], fraction_mile)


def _weather_points(routes: list[dict], interval: float) -> list[LatLon]:
    points: list[LatLon] = []
    for route in routes:
        for mile in checkpoint_miles(route["distance_mi"], interval):
            points.append(_along(route, mile))
        for mile in checkpoint_miles(route["distance_mi"], HEATMAP_INTERVAL_MI):
            points.append(_along(route, mile))
    return points


def _build_route(route, interval, departure, load_lbs, forecasts) -> dict:
    miles = checkpoint_miles(route["distance_mi"], interval)
    lengths = segment_miles(miles)
    checkpoints = []
    segments = []
    for index, (mile, length) in enumerate(zip(miles, lengths, strict=True)):
        point = _along(route, mile)
        fraction = 0 if route["distance_mi"] <= 0 else mile / route["distance_mi"]
        eta = departure + timedelta(seconds=route["duration_s"] * fraction)
        checkpoint = _checkpoint(index, mile, length, point, eta, load_lbs, forecasts)
        checkpoints.append(checkpoint)
        segments.append((checkpoint["level"], length))
    score = metrics_from_segments(route["id"], route["label"], segments, route["duration_min"])
    arrival = departure + timedelta(seconds=route["duration_s"])
    return {
        "id": route["id"],
        "label": route["label"],
        "geometry": encode_polyline6(route["geometry"]),
        "distance_mi": round(route["distance_mi"], 1),
        "duration_min": route["duration_min"],
        "arrival_eta": arrival.isoformat(),
        "summary": _summary(score),
        "checkpoints": checkpoints,
        "_score": score,
    }


def _checkpoint(index, mile, length, point, eta, load_lbs, forecasts) -> dict:
    series = forecasts.get((point.rounded().lat, point.rounded().lon))
    weather = None
    beyond = False
    wind = rain = snow = None
    if series is not None:
        hour_index, beyond = nearest_hour(series.times, eta)
        wind = _at(series.wind_mph, hour_index)
        rain = _at(series.rain_in_hr, hour_index)
        snow = _at(series.snow_in_hr, hour_index)
        if None not in (wind, rain, snow):
            weather = {
                "wind_mph": round(wind, 1),
                "rain_in_hr": round(rain, 3),
                "snow_in_hr": round(snow, 3),
            }
    classified = classify_conditions(
        wind_mph=wind,
        rain_in_hr=rain,
        snow_in_hr=snow,
        load_lbs=load_lbs,
        beyond_forecast=beyond and weather is not None,
    )
    return {
        "idx": index,
        "mile": round(mile, 1),
        "lat": round(point.lat, 5),
        "lon": round(point.lon, 5),
        "eta": eta.isoformat(),
        "weather": weather,
        "levels": {
            "wind": classified.levels.wind,
            "rain": classified.levels.rain,
            "snow": classified.levels.snow,
        },
        "level": classified.level,
        "segment_mi": round(length, 2),
        "reasons": classified.reasons,
        "status": classified.status,
    }


def _summary(score) -> dict:
    return {
        "severe_mi": round_miles(score.severe_mi),
        "high_mi": round_miles(score.high_mi),
        "moderate_mi": round_miles(score.moderate_mi),
        "low_mi": round_miles(score.low_mi),
        "no_travel_mi": round_miles(score.no_travel_mi),
        "unknown_mi": round_miles(score.unknown_mi),
        "avg_risk": None if score.avg_risk is None else round_risk(score.avg_risk),
        "max_level": score.max_level,
        "blocked": score.blocked,
    }


def _heatmap(routes, departure, load_lbs, forecasts) -> dict:
    points = []
    seen: set[tuple[float, float]] = set()
    for route in routes:
        for mile in checkpoint_miles(route["distance_mi"], HEATMAP_INTERVAL_MI):
            point = _along(route, mile).rounded()
            key = (point.lat, point.lon)
            if key in seen:
                continue
            seen.add(key)
            series = forecasts.get(key)
            levels = [
                _heatmap_level(series, departure + timedelta(hours=hour), load_lbs)
                for hour in range(49)
            ]
            points.append({"lat": point.lat, "lon": point.lon, "r": levels})
    return {"hours": 49, "start": departure.isoformat(), "points": points}


def _heatmap_level(series: HourlySeries | None, moment: datetime, load_lbs: float) -> int:
    if series is None:
        return -1
    index, beyond = nearest_hour(series.times, moment)
    if beyond:
        return -1
    classified = classify_conditions(
        wind_mph=_at(series.wind_mph, index),
        rain_in_hr=_at(series.rain_in_hr, index),
        snow_in_hr=_at(series.snow_in_hr, index),
        load_lbs=load_lbs,
    )
    if classified.level == "UNKNOWN":
        return -1
    return LEVEL_VALUE[classified.level]


def _at(values: list[float | None], index: int) -> float | None:
    if index < 0 or index >= len(values):
        return None
    return values[index]
