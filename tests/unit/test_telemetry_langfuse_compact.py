from __future__ import annotations

import pytest

from agent_framework.analytics.providers.langfuse import LangfuseAnalyticsPublisher
from agent_framework.observability.context import clear_observability_context, set_observability_context
from agent_framework.observability.telemetry import Telemetry


class Settings:
    ENABLE_LANGFUSE = False
    ENABLE_OTEL = False
    LANGFUSE_TRACE_MODE = "compact"


class FakeObservation:
    _next_id = 1

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.id = f"obs-{FakeObservation._next_id}"
        self.trace_id = "trace-123"
        FakeObservation._next_id += 1
        self.updates = []
        self.trace_updates = []
        self.trace_io_updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def update_trace(self, **kwargs):
        self.trace_updates.append(kwargs)

    def set_trace_io(self, **kwargs):
        self.trace_io_updates.append(kwargs)


class FakeContextManager:
    def __init__(self, observation):
        self.observation = observation

    def __enter__(self):
        return self.observation

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePropagationContext:
    def __init__(self, owner, kwargs):
        self.owner = owner
        self.kwargs = kwargs

    def __enter__(self):
        self.owner.propagations.append(self.kwargs)

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeLangfuse:
    def __init__(self, *, legacy_api: bool = False):
        self.observations = []
        self.propagations = []
        self.trace_updates = []
        self.flush_count = 0
        self.api = FakeApi() if legacy_api else None

    def start_as_current_observation(self, **kwargs):
        observation = FakeObservation(kwargs)
        self.observations.append(observation)
        return FakeContextManager(observation)

    def propagate_attributes(self, **kwargs):
        return FakePropagationContext(self, kwargs)

    def update_current_trace(self, **kwargs):
        self.trace_updates.append(kwargs)

    def flush(self):
        self.flush_count += 1


class FakeIngestionResponse:
    errors = []
    successes = []


class FakeIngestion:
    def __init__(self):
        self.batches = []

    def batch(self, *, batch, metadata=None):
        self.batches.append({"batch": batch, "metadata": metadata})
        return FakeIngestionResponse()


class FakeApi:
    def __init__(self):
        self.ingestion = FakeIngestion()


def telemetry_with_fake_langfuse(*, legacy_api: bool = False):
    FakeObservation._next_id = 1
    telemetry = Telemetry(Settings())
    telemetry.enabled = True
    telemetry.langfuse = FakeLangfuse(legacy_api=legacy_api)
    return telemetry


@pytest.mark.asyncio
async def test_compact_keeps_root_output_and_shows_ic_aga_noc_as_spans():
    clear_observability_context()
    telemetry = telemetry_with_fake_langfuse()

    async with telemetry.span("agent.gateway_message", session_id="s1", input={"request": "cms"}, _root_span=True) as span:
        await telemetry.event("IC.INTERNAL", {"step": "visible"}, kind="ic")
        await telemetry.event("NOC.001", {"step": "visible"}, kind="noc")
        await telemetry.event("AGA.010", {"step": "visible"}, kind="ic")
        span.set_output({"answer": "ok"})

    names = [obs.kwargs["name"] for obs in telemetry.langfuse.observations]
    assert names == ["agent.gateway_message", "IC.INTERNAL", "NOC.001", "AGA.010"]

    root = telemetry.langfuse.observations[0]
    assert root.updates[-1]["input"] == {"request": "cms"}
    assert root.updates[-1]["output"] == {"answer": "ok"}
    assert root.trace_io_updates[-1] == {"input": {"request": "cms"}, "output": {"answer": "ok"}}
    for observation in telemetry.langfuse.observations[1:]:
        assert observation.kwargs.get("trace_context") is None
        assert observation.kwargs["as_type"] == "span"

    ic = telemetry.langfuse.observations[1]
    assert ic.kwargs["input"]["step"] == "visible"
    assert ic.updates[-1]["input"]["step"] == "visible"
    assert ic.updates[-1]["output"] == {"status": "ok"}
    assert telemetry.langfuse.propagations[-1]["trace_name"] == "agent.gateway_message"

    aggregated = root.updates[-1]["metadata"]["aggregated_events"]
    assert [event["name"] for event in aggregated] == ["IC.INTERNAL", "NOC.001", "AGA.010"]


@pytest.mark.asyncio
async def test_analytics_control_event_is_a_span_and_not_a_trace_tag():
    clear_observability_context()
    set_observability_context(request_id="req-1", trace_id="req-1", session_id="s1")
    langfuse = FakeLangfuse()
    publisher = LangfuseAnalyticsPublisher(langfuse=langfuse)
    envelope = {
        "eventType": "IC.ORDER_CONFIRMED",
        "source": "agent_framework",
        "payload": {"tag": "IC.ORDER_CONFIRMED", "order_id": "order-1"},
        "metadata": {"ic": True},
    }

    await publisher.publish("IC.ORDER_CONFIRMED", envelope)

    assert [obs.kwargs["name"] for obs in langfuse.observations] == ["IC.ORDER_CONFIRMED"]
    observation = langfuse.observations[0]
    assert observation.kwargs["as_type"] == "span"
    assert observation.kwargs["input"] == envelope
    assert observation.updates[-1]["output"] == {"published": True}
    assert len(langfuse.trace_updates) == 1
    assert "tags" not in langfuse.trace_updates[0]


@pytest.mark.asyncio
async def test_compact_generation_records_io_model_parameters_and_usage_details():
    clear_observability_context()
    telemetry = telemetry_with_fake_langfuse()

    async with telemetry.span("agent.gateway_message", session_id="s1", input={"request": "cms"}, _root_span=True):
        async with telemetry.generation_span(
            name="llm.test",
            model="test-model",
            input=[{"role": "user", "content": "ping"}],
            metadata={"profile_name": "test"},
            model_parameters={"temperature": 0.2, "max_tokens": 100},
        ) as generation:
            generation.set_output("pong")
            generation.set_usage({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost_usd": 0.01})

    generation = telemetry.langfuse.observations[1]
    assert generation.kwargs["name"] == "llm.test"
    assert generation.kwargs["as_type"] == "generation"
    assert generation.kwargs["input"] == [{"role": "user", "content": "ping"}]
    assert generation.kwargs["model"] == "test-model"
    assert generation.kwargs["model_parameters"] == {"temperature": 0.2, "max_tokens": 100}
    assert "usage" not in generation.kwargs
    assert "usage_details" not in generation.kwargs
    assert generation.updates[-1]["input"] == [{"role": "user", "content": "ping"}]
    assert generation.updates[-1]["output"] == "pong"
    assert generation.updates[-1]["usage_details"] == {"input": 1, "output": 1}
    assert generation.updates[-1]["cost_details"] == {"total": 0.01}
    assert generation.kwargs.get("trace_context") is None


@pytest.mark.asyncio
async def test_legacy_io_fallback_updates_same_root_and_generation_observations():
    clear_observability_context()
    telemetry = telemetry_with_fake_langfuse(legacy_api=True)

    async with telemetry.span("agent.gateway_message", session_id="s1", input={"request": "cms"}, _root_span=True) as root:
        async with telemetry.generation_span(
            name="llm.test",
            model="test-model",
            input=[{"role": "user", "content": "ping"}],
            model_parameters={"temperature": 0.2},
        ) as generation:
            generation.set_output("pong")
            generation.set_usage({"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})
        root.set_output({"answer": "ok"})

    batches = telemetry.langfuse.api.ingestion.batches
    assert [event.type for item in batches for event in item["batch"]] == ["generation-update", "span-update"]

    generation_event = batches[0]["batch"][0]
    assert generation_event.body.id == "obs-2"
    assert generation_event.body.trace_id == "trace-123"
    assert generation_event.body.input == [{"role": "user", "content": "ping"}]
    assert generation_event.body.output == "pong"
    assert generation_event.body.usage_details == {"input": 2, "output": 3}

    root_event = batches[1]["batch"][0]
    assert root_event.body.id == "obs-1"
    assert root_event.body.trace_id == "trace-123"
    assert root_event.body.input == {"request": "cms"}
    assert root_event.body.output == {"answer": "ok"}
    assert len(telemetry.langfuse.observations) == 2

@pytest.mark.asyncio
async def test_langfuse_v4_module_level_propagation_sets_native_session_context():
    """SDK v4 propagation must receive the business session id natively."""
    clear_observability_context()
    telemetry = telemetry_with_fake_langfuse()
    calls = []

    def v4_propagate_attributes(**kwargs):
        calls.append(kwargs)
        return FakePropagationContext(telemetry.langfuse, kwargs)

    # Simulates ``from langfuse import propagate_attributes`` from SDK v4.
    telemetry._langfuse_propagate_attributes = v4_propagate_attributes

    async with telemetry.span(
        "agent.gateway_message",
        session_id="default:telecom_contas:session-123",
        user_id="11999999999",
        agent_id="telecom_contas",
        tenant_id="default",
        input={"message": "hello"},
        tags=["agent:telecom_contas"],
        _root_span=True,
    ):
        await telemetry.event("IC.TEST", {"ok": True}, kind="ic")

    assert len(calls) == 1
    assert calls[0]["session_id"] == "default:telecom_contas:session-123"
    assert calls[0]["user_id"] == "11999999999"
    assert calls[0]["trace_name"] == "agent.gateway_message"
    assert calls[0]["metadata"]["agent_id"] == "telecom_contas"
    assert calls[0]["metadata"]["tenant_id"] == "default"
    assert calls[0]["tags"] == ["agent:telecom_contas"]

    # Keep the legacy update as a compatibility fallback, but the v4 path above
    # is now the authoritative way to materialize native sessionId.
    root = telemetry.langfuse.observations[0]
    assert any(
        update.get("session_id") == "default:telecom_contas:session-123"
        for update in root.trace_updates
    )


def test_trace_attribute_propagation_keeps_legacy_client_method_fallback():
    telemetry = telemetry_with_fake_langfuse()
    telemetry._langfuse_propagate_attributes = None

    cm = telemetry._start_trace_attribute_propagation(
        "agent.gateway_message",
        {
            "session_id": "legacy-session",
            "user_id": "legacy-user",
            "agent_id": "legacy-agent",
        },
    )
    assert cm is not None
    with cm:
        pass
    assert telemetry.langfuse.propagations[-1]["session_id"] == "legacy-session"
