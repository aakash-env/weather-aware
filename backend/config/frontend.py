"""Serve the built React app from the same origin as the API."""

from django.conf import settings
from django.http import FileResponse, HttpResponse


def frontend(request, path: str = ""):
    dist = settings.FRONTEND_DIST.resolve()
    if path:
        candidate = (dist / path).resolve()
        if candidate.is_file() and dist in candidate.parents:
            return FileResponse(candidate.open("rb"))
    index = dist / "index.html"
    if index.is_file():
        return FileResponse(index.open("rb"))
    return HttpResponse(
        "The frontend build is missing. From frontend/, run npm install and npm run build.",
        status=503,
        content_type="text/plain",
    )
