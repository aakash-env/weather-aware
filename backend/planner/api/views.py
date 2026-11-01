from rest_framework.response import Response
from rest_framework.views import APIView

from planner.api.serializers import PlanRequestSerializer, error_detail
from planner.providers.base import ProviderError
from planner.services.factory import get_geocoder, get_planner
from planner.services.plan_trip import PlanningError


class HealthView(APIView):
    """Liveness probe. Does not call routing or weather providers."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class PlanView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = PlanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": error_detail(serializer.errors)}, status=400)
        try:
            result = get_planner().plan(serializer.validated_data)
        except PlanningError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return Response(result)


class GeocodeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response([])
        try:
            hits = get_geocoder().search(query, limit=5)
        except ProviderError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response([{"label": hit.label, "lat": hit.lat, "lon": hit.lon} for hit in hits])
