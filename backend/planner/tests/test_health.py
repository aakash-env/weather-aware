from rest_framework.test import APIClient


def test_health():
    response = APIClient().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
