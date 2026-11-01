"""Wire the live providers. Tests replace get_planner instead of calling this."""

from django.conf import settings
from django.core.cache import cache

from planner.providers.geocode_mapbox import MapboxGeocoder
from planner.providers.geocode_nominatim import FallbackGeocoder, NominatimGeocoder
from planner.providers.geocode_photon import PhotonGeocoder
from planner.providers.routing_mapbox import MapboxRouting
from planner.providers.routing_osrm import OsrmRouting
from planner.providers.weather_openmeteo import OpenMeteoWeather
from planner.services.plan_trip import TripPlanner


class _Cache:
    def get(self, key):
        return cache.get(key)

    def set(self, key, value, ttl):
        cache.set(key, value, ttl)


def get_planner() -> TripPlanner:
    if settings.MAPBOX_TOKEN:
        routing = MapboxRouting(settings.MAPBOX_TOKEN)
        geocoder = FallbackGeocoder(MapboxGeocoder(settings.MAPBOX_TOKEN), PhotonGeocoder())
        source = "mapbox"
    else:
        routing = OsrmRouting(settings.OSRM_BASE_URL)
        geocoder = FallbackGeocoder(PhotonGeocoder(), NominatimGeocoder())
        source = "osrm"
    weather = OpenMeteoWeather(cache=_Cache(), ttl_seconds=settings.WEATHER_CACHE_TTL)
    return TripPlanner(routing, geocoder, weather, routing_source=source)


def get_geocoder():
    return get_planner().geocoder
