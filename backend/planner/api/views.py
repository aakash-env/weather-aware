from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe. Does not call routing or weather providers."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})
