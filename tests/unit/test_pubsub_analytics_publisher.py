from __future__ import annotations

import sys
import types

import pytest

from agent_framework.analytics.providers.pubsub import PubSubAnalyticsPublisher


class _FakeFuture:
    def result(self, timeout: float | None = None) -> str:
        return "fake-message-id"


class _FakePublisherClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def publish(self, topic_path: str, *, data: bytes, **kwargs: str) -> _FakeFuture:
        self.calls.append((topic_path, data, kwargs))
        return _FakeFuture()


@pytest.fixture
def pubsub_publisher(monkeypatch: pytest.MonkeyPatch) -> PubSubAnalyticsPublisher:
    client = _FakePublisherClient()
    pubsub_v1 = types.ModuleType("google.cloud.pubsub_v1")
    pubsub_v1.PublisherClient = lambda: client  # type: ignore[attr-defined]
    google_cloud = types.ModuleType("google.cloud")
    google_cloud.pubsub_v1 = pubsub_v1  # type: ignore[attr-defined]
    google = types.ModuleType("google")
    google.cloud = google_cloud  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.pubsub_v1", pubsub_v1)
    monkeypatch.setenv("PUBSUB_EXCLUDED_EVENT_TYPES", "GRL.NATIVE_OUTPUT_GUARDRAILS")
    monkeypatch.setenv("PUBSUB_PAYLOAD_MODE", "legacy")

    publisher = PubSubAnalyticsPublisher(topic_path="projects/test/topics/analytics")
    publisher.client = client
    return publisher


@pytest.mark.asyncio
async def test_excluded_event_is_not_sent_to_pubsub(pubsub_publisher: PubSubAnalyticsPublisher) -> None:
    await pubsub_publisher.publish("GRL.NATIVE_OUTPUT_GUARDRAILS", {"session_id": "session-1"})

    assert pubsub_publisher.client.calls == []


@pytest.mark.asyncio
async def test_non_excluded_event_is_sent_to_pubsub(pubsub_publisher: PubSubAnalyticsPublisher) -> None:
    await pubsub_publisher.publish("GRL.002", {"session_id": "session-1"})

    assert len(pubsub_publisher.client.calls) == 1
    topic_path, _, attributes = pubsub_publisher.client.calls[0]
    assert topic_path == "projects/test/topics/analytics"
    assert attributes["event_type"] == "GRL.002"
