from django.urls import path

from planner.api.views import GeocodeView, HealthView, PlanView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("plan", PlanView.as_view(), name="plan"),
    path("geocode", GeocodeView.as_view(), name="geocode"),
]
