from types import SimpleNamespace

import pytest

from agent_framework.llm.base import LLMProvider
from agent_framework.llm.providers import (
    MockLLMProvider,
    OCISDKProvider,
    _extract_reasoning_content,
    _extract_openai_message_content,
    _extract_finish_reason,
)
from agent_framework.llm.types import LLMResponse


class LegacyOnlyProvider(LLMProvider):
    async def ainvoke(self, messages, **kwargs) -> str:
        return "legacy-answer"


@pytest.mark.asyncio
async def test_legacy_provider_gets_rich_response_fallback_without_breaking_contract():
    provider = LegacyOnlyProvider()

    legacy = await provider.ainvoke([{"role": "user", "content": "hello"}])
    rich = await provider.ainvoke_response([{"role": "user", "content": "hello"}])

    assert legacy == "legacy-answer"
    assert isinstance(legacy, str)
    assert isinstance(rich, LLMResponse)
    assert rich.content == legacy
    assert rich.reasoning_content is None


@pytest.mark.asyncio
async def test_mock_ainvoke_remains_string_and_rich_api_is_opt_in():
    provider = MockLLMProvider()
    messages = [{"role": "user", "content": "hello"}]

    legacy = await provider.ainvoke(messages)
    rich = await provider.ainvoke_response(messages)

    assert isinstance(legacy, str)
    assert legacy == rich.content
    assert rich.provider == "mock"
    assert rich.model == "mock-llm"
    assert rich.reasoning_content is None
    assert rich.usage["total_tokens"] > 0


def test_openai_compatible_reasoning_content_attribute_is_extracted():
    message = SimpleNamespace(content="answer", reasoning_content="model reasoning")
    assert _extract_reasoning_content(message) == "model reasoning"


def test_openai_compatible_reasoning_content_model_extra_is_extracted():
    message = SimpleNamespace(content="answer", model_extra={"reasoning_content": "extra reasoning"})
    assert _extract_reasoning_content(message) == "extra reasoning"


def test_missing_reasoning_content_is_none():
    message = SimpleNamespace(content="answer")
    assert _extract_reasoning_content(message) is None


def test_oci_sdk_reasoning_is_extracted_from_choice_message():
    message = SimpleNamespace(content="answer", reasoning_content="oci reasoning")
    choice = SimpleNamespace(message=message)
    chat_response = SimpleNamespace(choices=[choice])
    response = SimpleNamespace(data=SimpleNamespace(chat_response=chat_response))

    assert OCISDKProvider._extract_reasoning_content(response) == "oci reasoning"


def test_openai_compatible_plain_string_content_is_preserved():
    message = SimpleNamespace(content='{"decision":"KEEP"}')
    assert _extract_openai_message_content(message) == '{"decision":"KEEP"}'


def test_openai_compatible_list_content_is_joined():
    message = SimpleNamespace(content=[
        SimpleNamespace(text='{"decision":'),
        {"text": '"KEEP"}'},
    ])
    assert _extract_openai_message_content(message) == '{"decision":"KEEP"}'


def test_openai_compatible_dict_message_and_content_are_supported():
    message = {"content": [{"text": "{\"ok\":true}"}]}
    assert _extract_openai_message_content(message) == '{"ok":true}'


def test_openai_compatible_unknown_content_fails_closed_to_empty_string():
    message = SimpleNamespace(content=object())
    assert _extract_openai_message_content(message) == ""


def test_openai_compatible_reasoning_is_not_used_as_answer_fallback():
    message = SimpleNamespace(content=None, reasoning_content='{"decision":"KEEP"}')
    assert _extract_openai_message_content(message) == ""
    assert _extract_reasoning_content(message) == '{"decision":"KEEP"}'


def test_finish_reason_is_extracted_from_object_and_dict():
    assert _extract_finish_reason(SimpleNamespace(finish_reason="length")) == "length"
    assert _extract_finish_reason({"finish_reason": "stop"}) == "stop"
