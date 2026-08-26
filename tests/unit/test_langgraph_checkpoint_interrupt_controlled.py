import base64
import json
from types import SimpleNamespace

import pytest

from agent_framework.checkpoints.langgraph_saver import (
    RepositoryCheckpointSaver,
    _TYPED_SERDE_MARKER,
    _decode_checkpoint_value,
    _encode_checkpoint_value,
    _encode_pending_write_value,
)


Interrupt = type("Interrupt", (), {})
Interrupt.__module__ = "langgraph.types"


class FakeSerde:
    def dumps_typed(self, value):
        assert type(value).__module__ == "langgraph.types"
        assert type(value).__qualname__ == "Interrupt"
        return "msgpack", b"interrupt-payload"

    def loads_typed(self, typed):
        type_name, payload = typed
        assert type_name == "msgpack"
        assert payload == b"interrupt-payload"
        return Interrupt()


class MemoryRepo:
    def __init__(self):
        self.value = None

    async def put(self, thread_id, value):
        self.value = value

    async def get_latest(self, thread_id):
        return self.value


def test_checkpoint_interrupt_only_in_special_channel_round_trips():
    serde = FakeSerde()
    raw_interrupt = Interrupt()
    checkpoint = {
        "id": "cp1",
        "channel_values": {
            "__root__": {
                "__interrupt__": [raw_interrupt],
                "business": {"ok": True},
            },
            "ordinary": {"value": 1},
        },
    }

    encoded = _encode_checkpoint_value(serde, checkpoint)
    leaf = encoded["channel_values"]["__root__"]["__interrupt__"][0]
    assert leaf[_TYPED_SERDE_MARKER] is True
    assert leaf["type"] == "msgpack"
    assert base64.b64decode(leaf["data"]) == b"interrupt-payload"
    assert encoded["channel_values"]["ordinary"] == {"value": 1}

    decoded = _decode_checkpoint_value(serde, encoded)
    assert type(decoded["channel_values"]["__root__"]["__interrupt__"][0]).__module__ == "langgraph.types"
    assert decoded["channel_values"]["ordinary"] == {"value": 1}


def test_checkpoint_interrupt_outside_special_channel_is_rejected():
    serde = FakeSerde()
    checkpoint = {
        "id": "cp1",
        "channel_values": {"ordinary": [Interrupt()]},
    }
    with pytest.raises(TypeError, match="não serializável"):
        _encode_checkpoint_value(serde, checkpoint)


def test_checkpoint_unknown_object_inside_interrupt_channel_is_rejected():
    serde = FakeSerde()

    class Unknown:
        pass

    checkpoint = {
        "id": "cp1",
        "channel_values": {"__root__": {"__interrupt__": [Unknown()]}},
    }
    with pytest.raises(TypeError, match="não serializável"):
        _encode_checkpoint_value(serde, checkpoint)


def test_plain_checkpoint_keeps_plain_json_shape():
    serde = FakeSerde()
    checkpoint = {
        "id": "cp1",
        "channel_values": {"x": {"nested": [1, "a", True, None]}},
        "channel_versions": {"x": "1"},
    }
    encoded = _encode_checkpoint_value(serde, checkpoint)
    assert encoded == checkpoint
    assert _TYPED_SERDE_MARKER not in json.dumps(encoded)


def test_pending_write_interrupt_requires_interrupt_branch():
    serde = FakeSerde()
    encoded = _encode_pending_write_value(
        serde,
        {"__interrupt__": [Interrupt()]},
        path="$.pending_writes[t].__root__",
    )
    assert encoded["__interrupt__"][0][_TYPED_SERDE_MARKER] is True

    with pytest.raises(TypeError, match="não serializável"):
        _encode_pending_write_value(
            serde,
            {"ordinary": [Interrupt()]},
            path="$.pending_writes[t].__root__",
        )


def test_aput_encodes_only_checkpoint_interrupt_and_keeps_other_sections_strict():
    repo = MemoryRepo()
    settings = SimpleNamespace(CHECKPOINT_REPOSITORY_PROVIDER="memory")
    saver = RepositoryCheckpointSaver(settings, repository=repo)
    saver.serde = FakeSerde()

    checkpoint = {
        "id": "cp1",
        "channel_values": {"__root__": {"__interrupt__": [Interrupt()]}},
    }

    import asyncio
    asyncio.run(saver.aput(
        {"configurable": {"thread_id": "t1"}},
        checkpoint,
        {"source": "test"},
        {"x": 1},
    ))

    assert repo.value["metadata"] == {"source": "test"}
    assert repo.value["new_versions"] == {"x": 1}
    assert repo.value["checkpoint"]["channel_values"]["__root__"]["__interrupt__"][0][_TYPED_SERDE_MARKER] is True


def test_aput_does_not_enable_typed_serde_for_metadata():
    repo = MemoryRepo()
    settings = SimpleNamespace(CHECKPOINT_REPOSITORY_PROVIDER="memory")
    saver = RepositoryCheckpointSaver(settings, repository=repo)
    saver.serde = FakeSerde()

    import asyncio
    with pytest.raises(TypeError, match="metadata"):
        asyncio.run(saver.aput(
            {"configurable": {"thread_id": "t1"}},
            {"id": "cp1", "channel_values": {"x": 1}},
            {"bad": Interrupt()},
            {},
        ))
