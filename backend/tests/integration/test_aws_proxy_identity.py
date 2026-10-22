"""AU4: the proxy middleware used by the deployment preserves per-client limits.

Real Caddy header replacement is checked by deploy/aws/test_gate.py; these tests use
real Uvicorn middleware and the real login limiter, with isolated database fixtures.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app

CADDY_IP = "172.30.64.2"


@pytest.fixture
def proxy(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ProxyHeadersMiddleware]:
    monkeypatch.setattr(settings, "auth_mode", "session")
    limiter.clear()
    app.dependency_overrides[get_db] = lambda: production_seeded
    try:
        yield ProxyHeadersMiddleware(app, trusted_hosts=[CADDY_IP])
    finally:
        app.dependency_overrides.pop(get_db, None)
        limiter.clear()


def attempt(client: TestClient, forwarded_ip: str, staff_id: int) -> int:
    return client.post(
        "/auth/login",
        json={"staff_id": staff_id, "password": "wrong-password"},
        headers={"Origin": settings.cors_origins[0], "X-Forwarded-For": forwarded_ip},
    ).status_code


def test_caddy_client_addresses_use_separate_login_buckets(proxy: ProxyHeadersMiddleware) -> None:
    with TestClient(proxy, base_url="https://testserver", client=(CADDY_IP, 1234)) as client:
        for i in range(10):
            assert attempt(client, "203.0.113.10", 99000 + i) == 401
        assert attempt(client, "203.0.113.10", 99010) == 429
        # Another real client is not counted as the same Caddy address.
        assert attempt(client, "203.0.113.11", 99011) == 401


def test_other_peers_cannot_escape_limits_by_forging_forwarded_for(
    proxy: ProxyHeadersMiddleware,
) -> None:
    with TestClient(proxy, base_url="https://testserver", client=("172.30.64.99", 1234)) as client:
        for i in range(10):
            assert attempt(client, f"203.0.113.{i + 1}", 99000 + i) == 401
        assert attempt(client, "203.0.113.200", 99010) == 429
