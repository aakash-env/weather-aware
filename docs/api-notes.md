# API spike notes

Recorded from live calls on 2026-11-01 (Chicago → Denver unless noted). Scripts: `scripts/spike_apis.py`, `scripts/spike_limits.py`. Mapbox was not called: `MAPBOX_TOKEN` was not set. Parser behavior for Mapbox follows the current Directions and Geocoding docs and is covered by fixture tests, not a live response.

## Routing

### OSRM (public demo)

- URL: `https://router.project-osrm.org/route/v1/driving/{lon},{lat};{lon},{lat}?alternatives=3&overview=full&geometries=polyline6`
- Chicago → Denver returned **2** routes, `code=Ok` (not 3).
  - Route 0: 1,617,555 m, 64,097 s, polyline6 length 43,703 chars
  - Route 1: 1,793,369 m, 71,622 s
- Route object keys: `distance` (meters), `duration` (seconds), `geometry` (polyline6), `legs`, `weight`, `weight_name`.
- No rate-limit headers on these calls.
- A third corridor is available only as its own request. Via `(-100.5, 43.5)` returned 1 route, 1,279 mi. Via `(-100.5, 37.2)` returned 1 route, 1,311 mi. Both differ from the direct alternatives. The app may request one via only when the direct call returns fewer than 3 routes. It never invents geometry.

### Mapbox Directions (docs, not live)

- `GET /directions/v5/mapbox/driving/{lon,lat};{lon,lat}?alternatives=true&geometries=polyline6&overview=full`
- Docs: `alternatives=true` may return **up to two alternatives** in addition to the primary route, so the `routes` array length is 0–3. An alternative is not guaranteed.
- Each route includes `distance` (meters), `duration` (seconds), and `geometry` (polyline6 when requested).
- If the token is missing, routing uses OSRM. If Mapbox returns fewer than 3, the same via-waypoint fallback runs.

## Geocoding

### Photon

- `https://photon.komoot.io/api/?q=Chicago&limit=3` returned features with `geometry.coordinates` as `[lon, lat]` and `properties.name`, `state`, `country`.
- Used when `MAPBOX_TOKEN` is unset.

### Nominatim

- `https://nominatim.openstreetmap.org/search?q=Denver,%20CO&format=jsonv2` worked with a descriptive User-Agent. One result per second is the published policy, so it is only a backup if Photon fails.

### Mapbox Geocoding

- Not called live. The client uses Geocoding v5 `mapbox.places`: `features[].place_name` and `center: [lon, lat]`.

## Weather (Open-Meteo)

- `https://api.open-meteo.com/v1/forecast`
- Params that worked: `hourly=wind_speed_10m,rain,showers,snowfall`, `wind_speed_unit=mph`, `precipitation_unit=inch`, `timezone=GMT`.
- `hourly_units`: wind `mp/h` (values are miles per hour; Chicago peak in the sample was 16.1), rain/showers/snowfall `inch`.
- A single coordinate returns one JSON object. Several coordinates return a **JSON array** in request order (verified at 3, 10, and 50 locations).
- No rate-limit headers were present. Batches of 50 completed in about 1.3 s. The client uses batches of 50 and at most 4 concurrent batches.
- `forecast_days=3` is **not** “72 hours from departure”. It is three calendar days starting at 00:00 UTC **today** (on this run: `2026-11-01T00:00` through `2026-11-03T23:00`, 72 values).
- `forecast_days=7` → 168 hours; `forecast_days=16` → 384 hours (through `2026-11-16T23:00`). The free forecast endpoint accepts 16 days, which matches the “reject departures more than 16 days ahead” rule.
- `forecast_hours=96` starts at the current UTC hour (`2026-11-01T05:00` on this run), not midnight. Passing it together with `forecast_days` limited the series to `forecast_hours`.
- Design adjustment: request `forecast_days` = the number of UTC calendar days from today through `departure + 72h`, capped at 16. Do not hard-code 3. Checkpoint ETAs past the returned series are clamped and flagged `beyond_forecast`.
- Rain risk uses `rain + showers` (both inches). They are separate fields and both can be non-zero in the same hour. Snow risk uses `snowfall` as depth in inches for that hour.

## What this changes

- Fewer than 3 routes is a normal OSRM (and possible Mapbox) result. The UI must say so.
- Weather coverage is based on today’s date plus up to 16 forecast days, not a fixed 3-day blob.
- Missing hours stay `unknown`. They are not filled in as Low.
