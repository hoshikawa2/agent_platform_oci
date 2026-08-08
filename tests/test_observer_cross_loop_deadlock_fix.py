from __future__ import annotations

import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from agent_framework import observer
from agent_framework.analytics import tim_sequence


def test_sync_event_calls_share_one_stable_asyncio_loop(monkeypatch):
    seen_loop_ids: set[int] = set()
    seen_lock = threading.Lock()

    async def fake_aevent(name: str, **kwargs):
        loop_id = id(asyncio.get_running_loop())
        with seen_lock:
            seen_loop_ids.add(loop_id)
        await asyncio.sleep(0.01)
        return {"eventType": name, "loop_id": loop_id}

    monkeypatch.setattr(observer, "aevent", fake_aevent)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: observer.event(f"IC.TEST.{i}"), range(24)))

    assert len(seen_loop_ids) == 1
    assert {item["loop_id"] for item in results} == seen_loop_ids


def test_memory_sequence_is_safe_across_independent_event_loops(monkeypatch):
    monkeypatch.setenv("PUBSUB_SEQUENCE_ENABLED", "true")
    monkeypatch.setenv("PUBSUB_SEQUENCE_PROVIDER", "memory")
    tim_sequence._memory_counters.clear()

    def one_call(_: int) -> int | None:
        return asyncio.run(
            tim_sequence.next_sequence(
                "agent-a",
                "session-a",
                "transaction-cross-loop",
            )
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        values = list(pool.map(one_call, range(120)))

    assert sorted(values) == list(range(1, 121))


def test_mongo_ttl_index_guard_is_thread_safe_across_event_loops(monkeypatch):
    tim_sequence._mongo_index_checked = False
    monkeypatch.setenv("PUBSUB_SEQUENCE_MONGODB_URI", "mongodb://fake")

    calls = 0
    calls_lock = threading.Lock()

    class FakeCollection:
        def create_index(self, *args, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            # Enlarge the contention window that previously exposed the
            # cross-event-loop asyncio.Lock issue.
            time.sleep(0.05)

    class FakeDatabase:
        def __getitem__(self, name):
            return FakeCollection()

    class FakeMongoClient:
        def __init__(self, uri):
            self.uri = uri

        def __getitem__(self, name):
            return FakeDatabase()

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "pymongo", SimpleNamespace(MongoClient=FakeMongoClient))

    def ensure_index(_: int) -> None:
        asyncio.run(tim_sequence._ensure_mongo_ttl_index_once(60))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(ensure_index, range(16)))

    assert calls == 1
    assert tim_sequence._mongo_index_checked is True
