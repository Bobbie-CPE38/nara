"""The suite's LLM defaults and Bedrock guard survive a developer's real .env (R6-Q15 ก)."""

import os
from decimal import Decimal

import pytest

from app.core.config import Settings, settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmRequest, bedrock
from app.services import llm_service


def test_llm_defaults_are_fake_and_off_for_existing_and_new_settings() -> None:
    assert os.environ["LLM_PROVIDER"] == "fake" and os.environ["LLM_ENABLED"] == "false"
    assert settings.llm_provider == "fake" and settings.llm_enabled is False
    fresh = Settings()
    assert fresh.llm_provider == "fake" and fresh.llm_enabled is False


@pytest.mark.parametrize("through_service", [False, True])
def test_an_accidental_real_bedrock_call_fails_the_test(
    monkeypatch: pytest.MonkeyPatch, through_service: bool
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", "test-model")
    monkeypatch.setattr(settings, "aws_region", "ap-southeast-1")
    monkeypatch.setattr(settings, "llm_input_price_per_mtok_usd", Decimal("0.41"))
    request = LlmRequest(
        system="s", prompt="p", payload={}, max_output_tokens=10, timeout_seconds=1
    )

    # The adapter catches Exception; the guard's failure must still get out
    with pytest.raises(pytest.fail.Exception, match="Unmocked Bedrock call"):
        if through_service:
            llm_service.generate_explanation(request)
        else:
            bedrock.generate(request)


def test_the_guard_leaves_a_missing_config_answer_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", None)
    request = LlmRequest(
        system="s", prompt="p", payload={}, max_output_tokens=10, timeout_seconds=1
    )
    assert bedrock.generate(request).status == LlmCallStatus.CONFIG_ERROR
