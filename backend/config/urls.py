from django.urls import include, path, re_path

from config.frontend import frontend

urlpatterns = [
    path("api/", include("planner.api.urls")),
    re_path(r"^(?P<path>.*)$", frontend, name="frontend"),
]
