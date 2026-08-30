from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

import pytest

from agent_framework.guardrails.calibrated.llm_client import GuardrailLLMClient
from agent_framework.llm.providers import OCICompatibleOpenAIProvider
from agent_framework.observability.context import (
    clear_observability_context,
    get_observability_context,
    set_observability_context,
)


def test_openai_langfuse_wrapper_is_disabled_inside_active_framework_trace(monkeypatch):
    """A correlated request must never create a standalone OpenAI-generation trace."""
    clear_observability_context()
    set_observability_context(request_id="req-123", trace_id="trace-123")
    monkeypatch.setenv("ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION", "true")

    provider = OCICompatibleOpenAIProvider.__new__(OCICompatibleOpenAIProvider)
    provider.telemetry = None  # compatibility path: no Telemetry explicitly injected
    settings = SimpleNamespace(
        ENABLE_LANGFUSE=True,
        ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=True,
    )

    fake_openai = ModuleType("openai")
    class AsyncOpenAI:
        pass
    AsyncOpenAI.__module__ = "openai"
    fake_openai.AsyncOpenAI = AsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    client_cls = provider._resolve_async_openai(settings)

    # Standard OpenAI client = framework owns observability/correlation.
    assert client_cls.__module__.startswith("openai")
    assert "langfuse" not in client_cls.__module__
    clear_observability_context()


@pytest.mark.asyncio
async def test_guardrail_sync_bridge_preserves_observability_context_in_worker(monkeypatch):
    """Legacy sync guardrail bridge must carry request/trace ContextVars to its worker."""
    clear_observability_context()
    set_observability_context(request_id="req-guardrail", trace_id="trace-guardrail")

    import agent_framework.guardrails.framework_llm_client as framework_client

    async def fake_classifier(llm, task, payload, **kwargs):
        ctx = get_observability_context()
        return {"request_id": ctx.request_id, "trace_id": ctx.trace_id, "task": task}

    monkeypatch.setattr(framework_client, "classify_with_framework_llm", fake_classifier)

    result = GuardrailLLMClient._run_framework_classifier("TOX", {"text": "ok"})

    assert result["request_id"] == "req-guardrail"
    assert result["trace_id"] == "trace-guardrail"
    assert result["task"] == "TOX"
    clear_observability_context()
