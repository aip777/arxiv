import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_reports_database_ok():
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_unknown_url_returns_json_404(settings):
    settings.DEBUG = False
    response = APIClient().get("/api/does-not-exist/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}
