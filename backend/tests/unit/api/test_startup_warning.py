"""APP_ENV=aws with AUTH_MODE=demo warns at startup (docs/workflow.md 6.33.1, PR AU1)."""

import logging

import pytest

from app import main
from app.core.config import settings


@pytest.mark.parametrize(
    ("app_env", "auth_mode", "warns"),
    [("aws", "demo", True), ("aws", "session", False), ("dev", "demo", False)],
)
def test_demo_mode_on_aws_warns_without_stopping(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    app_env: str,
    auth_mode: str,
    warns: bool,
) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "auth_mode", auth_mode)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        main.warn_if_demo_on_aws()

    assert any("AUTH_MODE=demo" in record.message for record in caplog.records) is warns
