from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent_framework.checkpoints.langgraph_saver import (
    RepositoryCheckpointSaver,
    _durable_config,
)


class _Repo:
    def __init__(self) -> None:
        self.saved = None

    async def put(self, thread_id, checkpoint):
        self.saved = (thread_id, checkpoint)

    async def get_latest(self, thread_id):
        return self.saved[1] if self.saved and self.saved[0] == thread_id else None


def test_private_pregel_runtime_is_not_durable() -> None:
    config = {
        "tags": ["x"],
        "configurable": {
            "thread_id": "t1",
            "tenant": "default",
            "__pregel_runtime": "stringified-runtime",
            "__pregel_store": "stringified-store",
        },
    }

    cleaned = _durable_config(config)

    assert cleaned == {
        "tags": ["x"],
        "configurable": {"thread_id": "t1", "tenant": "default"},
    }
    assert "__pregel_runtime" in config["configurable"]


def test_saver_strips_private_runtime_before_put_and_restore() -> None:
    repo = _Repo()
    saver = RepositoryCheckpointSaver(SimpleNamespace(), repository=repo)
    config = {
        "configurable": {
            "thread_id": "t1",
            "__pregel_runtime": "Runtime(...) persisted by JSON backend",
        }
    }
    checkpoint = {"id": "cp1", "v": 1}

    returned = asyncio.run(saver.aput(config, checkpoint, {}, {}))
    assert returned["configurable"] == {"thread_id": "t1", "checkpoint_id": "cp1"}
    assert repo.saved is not None
    persisted = repo.saved[1]
    assert "__pregel_runtime" not in persisted["config"]["configurable"]

    # Also protects legacy records already stored with a stringified runtime.
    persisted["config"]["configurable"]["__pregel_runtime"] = "legacy-string"
    restored = saver._make_tuple(persisted)
    restored_config = restored.config if hasattr(restored, "config") else restored["config"]
    assert "__pregel_runtime" not in restored_config["configurable"]
