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
    assert returned["configurable"] == {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "cp1"}
    assert repo.saved is not None
    persisted = repo.saved[1]
    assert "__pregel_runtime" not in persisted["config"]["configurable"]

    # Also protects legacy records already stored with a stringified runtime.
    persisted["config"]["configurable"]["__pregel_runtime"] = "legacy-string"
    restored = saver._make_tuple(persisted)
    restored_config = restored.config if hasattr(restored, "config") else restored["config"]
    assert "__pregel_runtime" not in restored_config["configurable"]


def test_nested_pregel_runtime_is_removed_from_checkpoint_and_pending_writes() -> None:
    repo = _Repo()
    saver = RepositoryCheckpointSaver(SimpleNamespace(), repository=repo)
    config = {"configurable": {"thread_id": "t-nested"}}
    checkpoint = {
        "id": "cp-nested",
        "v": 1,
        "channel_values": {
            "__pregel_tasks": {"durable": True},
            "task": {
                "config": {
                    "configurable": {
                        "thread_id": "t-nested",
                        "__pregel_runtime": "Runtime(...) nested",
                        "business_key": "kept",
                    }
                }
            }
        },
    }

    asyncio.run(saver.aput(config, checkpoint, {}, {}))
    asyncio.run(
        saver.aput_writes(
            config,
            [
                (
                    "tasks",
                    {
                        "nested": {
                            "configurable": {
                                "__pregel_runtime": "Runtime(...) write",
                                "subject": "TIM Fashion",
                            }
                        }
                    },
                )
            ],
            "task-1",
        )
    )

    assert repo.saved is not None
    persisted = repo.saved[1]
    assert persisted["checkpoint"]["channel_values"]["__pregel_tasks"] == {"durable": True}
    task_config = persisted["checkpoint"]["channel_values"]["task"]["config"]["configurable"]
    assert "__pregel_runtime" not in task_config
    assert task_config["business_key"] == "kept"
    pending_cfg = persisted["pending_writes"][0]["value"]["nested"]["configurable"]
    assert "__pregel_runtime" not in pending_cfg
    assert pending_cfg["subject"] == "TIM Fashion"


def test_restore_rebuilds_fresh_canonical_config_instead_of_rebinding_stored_config() -> None:
    repo = _Repo()
    saver = RepositoryCheckpointSaver(SimpleNamespace(), repository=repo)
    legacy_payload = {
        "thread_id": "thread-legacy",
        "checkpoint_id": "cp-legacy",
        "config": {
            "tags": ["old-run"],
            "configurable": {
                "thread_id": "thread-legacy",
                "checkpoint_ns": "wf",
                "checkpoint_id": "cp-legacy",
                "tenant": "default",
                "__pregel_runtime": "stringified-runtime",
                "__pregel_store": "stringified-store",
            },
        },
        "checkpoint": {"id": "cp-legacy", "v": 1},
        "metadata": {},
    }
    asyncio.run(repo.put("thread-legacy", legacy_payload))

    # Simulate a new invocation. Runtime/private keys supplied by a previous run
    # must never be rebound from the persisted checkpoint tuple.
    request = {
        "tags": ["new-run"],
        "configurable": {
            "thread_id": "thread-legacy",
            "checkpoint_ns": "wf",
            "__pregel_runtime": "request-runtime-placeholder",
        },
    }
    restored = asyncio.run(saver.aget_tuple(request))
    restored_config = restored.config if hasattr(restored, "config") else restored["config"]

    assert restored_config == {
        "configurable": {
            "thread_id": "thread-legacy",
            "checkpoint_ns": "wf",
            "checkpoint_id": "cp-legacy",
        }
    }
    assert "tags" not in restored_config
    assert "tenant" not in restored_config["configurable"]
    assert "__pregel_runtime" not in restored_config["configurable"]


def test_legacy_checkpoint_structural_json_strings_are_recovered() -> None:
    from agent_framework.checkpoints.langgraph_saver import _normalize_checkpoint, _normalize_config

    legacy = {
        "v": 1,
        "id": "cp-json",
        "channel_values": '{"state":{"ok":true}}',
        "channel_versions": '{"state":"0001"}',
        "versions_seen": '{"node":"{\\"state\\":\\"0001\\"}"}',
    }
    normalized = _normalize_checkpoint(legacy)
    assert normalized["channel_values"] == {"state": {"ok": True}}
    assert normalized["channel_versions"] == {"state": "0001"}
    assert normalized["versions_seen"] == {"node": {"state": "0001"}}

    cfg = _normalize_config({"configurable": '{"thread_id":"t1","checkpoint_ns":""}'})
    assert cfg["configurable"] == {"thread_id": "t1", "checkpoint_ns": ""}


def test_checkpoint_serialization_never_silently_stringifies_unknown_objects() -> None:
    import pytest
    from agent_framework.checkpoints.langgraph_saver import _strict_json_value

    class RuntimeLike:
        def override(self):
            return self

    with pytest.raises(TypeError, match="Checkpoint contém valor não serializável"):
        _strict_json_value({"channel_values": {"bad": RuntimeLike()}}, path="$.checkpoint")
