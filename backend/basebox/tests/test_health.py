import pytest
from rest_framework.test import APIClient

from basebox.models import ErrorLog

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


def test_unhandled_error_returns_json_500_and_is_recorded(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom api_key=sk-secret")

    monkeypatch.setattr("papers.views.build_stats", boom)
    response = APIClient(raise_request_exception=False).get("/api/stats/")

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred."}
    log = ErrorLog.objects.get()
    assert (log.level, log.path, log.method, log.status_code) == ("ERROR", "/api/stats/", "GET", 500)
    assert "RuntimeError: boom" in log.traceback
    assert "sk-secret" not in log.traceback


def test_client_errors_are_not_recorded():
    response = APIClient().get("/api/stats/", {"top_n": 0})
    assert response.status_code == 400
    assert "top_n" in response.json()["detail"]
    assert not ErrorLog.objects.exists()
