"""The Thai wording rules of the two prompts (round 6, found in the first live Lambda run).

The live answers mixed in Chinese, wrote field names (ranking_key, effective_minimum) and
plan ids, used markdown, and called a shortage a failure. The prompt now forbids each of
these and defines the terms; these tests keep the rules and the glossary in step with the
payload, since a model can only be told about fields the payload really has.
"""

import pytest

from app.core.config import settings
from app.integrations.llm import LlmRequest
from app.services import case_summary_service, explanation_service, llm_gateway

PROMPTS = {
    "rank explanation": explanation_service.SYSTEM_PROMPT,
    "case summary": case_summary_service.SYSTEM_PROMPT,
}


@pytest.mark.parametrize("prompt", PROMPTS.values(), ids=PROMPTS.keys())
def test_both_prompts_ask_for_plain_thai_without_markdown_or_field_names(prompt: str) -> None:
    assert "Thai" in prompt
    assert "no markdown" in prompt
    assert "Never write a field name" in prompt


def test_the_explanation_prompt_defines_every_item_of_the_ranking_key() -> None:
    prompt = explanation_service.SYSTEM_PROMPT
    # staff_id only breaks a final tie and is never explained
    for item in explanation_service.RANKING_KEY_ORDER:
        if item != "staff_id":
            assert item in prompt


def test_the_explanation_prompt_keeps_its_earlier_rules() -> None:
    prompt = explanation_service.SYSTEM_PROMPT
    assert "plan_penalty.meaning says what chose the first wave." in prompt
    assert 'Refer to people only as "อันดับ N"' in prompt
    assert "Never claim that a rank comes from the total points." in prompt


def test_the_explanation_prompt_ties_reserve_to_the_first_wave_field() -> None:
    """Live run: all three candidates were first_wave true and the answer called them reserves."""
    prompt = explanation_service.SYSTEM_PROMPT
    assert "first_wave: true means" in prompt
    assert "only from that field" in prompt
    assert "never call any of them a reserve" in prompt
    assert "name that item and both values" in prompt


def test_the_summary_prompt_copies_timestamps_and_forbids_other_calendars() -> None:
    """Live run: the model wrote 2566 for 2026, which the number check rightly rejected."""
    prompt = case_summary_service.SYSTEM_PROMPT
    assert "Copy every date and time exactly as it is written" in prompt
    assert "no Buddhist-era year" in prompt
    assert "เวร" in prompt


def test_the_summary_prompt_keeps_its_earlier_rules_and_names_a_shortage() -> None:
    prompt = case_summary_service.SYSTEM_PROMPT
    assert "unless case_status is RESOLVED" in prompt
    assert "do not subtract" in prompt
    assert "Asia/Bangkok" in prompt
    assert "ขาดอีก N คน" in prompt
    assert "ความล้มเหลว" in prompt  # named only to forbid it for a shortage


def test_the_prompt_versions_changed_with_the_wording() -> None:
    """A new version makes a plan or case ask again, so an answer written under the old
    wording is not shown as the current one."""
    assert explanation_service.PROMPT_VERSION == "rank-explanation-v4"
    assert case_summary_service.PROMPT_VERSION == "case-summary-v3"


def test_the_longer_prompts_leave_room_under_the_input_limit() -> None:
    for prompt in PROMPTS.values():
        request = LlmRequest(
            system=prompt, prompt="", payload={}, max_output_tokens=1, timeout_seconds=1
        )
        assert llm_gateway.estimate_input_tokens(request) < settings.llm_max_input_tokens // 4
