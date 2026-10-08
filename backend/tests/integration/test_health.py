from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_ok_with_database() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
