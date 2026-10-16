"""The suite's LINE defaults and network guard survive a developer's real mode."""

import os

import pytest
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.integrations.line import client
from app.services.line_webhook_service import send_reply


def test_line_defaults_are_simulation_for_existing_and_new_settings() -> None:
    assert os.environ["LINE_MODE"] == "simulation"
    assert settings.line_mode == "simulation"
    assert Settings().line_mode == "simulation"


@pytest.mark.parametrize("method", ["push", "reply", "best_effort_reply"])
def test_accidental_real_mode_cannot_call_line(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-token"))
    assert settings.real_line_enabled

    with pytest.raises(pytest.fail.Exception, match="Unmocked LINE HTTP call"):
        if method == "push":
            client.push({"to": "U_TEST", "messages": []}, "test-retry-key")
        elif method == "reply":
            client.reply("test-reply-token", "test-message")
        else:
            # The production wrapper catches Exception; the guard must still fail.
            send_reply("test-reply-token", "test-message")
