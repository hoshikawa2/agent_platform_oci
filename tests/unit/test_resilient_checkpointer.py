import pytest

from agent_framework.checkpoints.checkpoint_repository import (
    CheckpointRecoveryError,
    InMemoryCheckpointRepository,
    ResilientCheckpointRepository,
)


@pytest.mark.asyncio
async def test_integrity_envelope_and_recovery_skips_corrupt_latest():
    raw = InMemoryCheckpointRepository()
    repo = ResilientCheckpointRepository(raw, compact_every=100, keep_last=10, recovery_scan_limit=5)

    await repo.put("thread-1", {"checkpoint_id": "ok-1", "checkpoint": {"id": "ok-1", "value": 1}})
    await repo.put("thread-1", {"checkpoint_id": "ok-2", "checkpoint": {"id": "ok-2", "value": 2}})

    # Simula corrupção no último registro persistido.
    raw._data["thread-1"][-1]["payload"]["checkpoint"]["value"] = 999

    recovered = await repo.get_latest("thread-1")
    assert recovered["checkpoint_id"] == "ok-1"
    assert recovered["checkpoint"]["value"] == 1


@pytest.mark.asyncio
async def test_compaction_keeps_last_n_checkpoints():
    raw = InMemoryCheckpointRepository()
    repo = ResilientCheckpointRepository(raw, compact_every=1, keep_last=3, recovery_scan_limit=10)

    for i in range(7):
        await repo.put("thread-compact", {"checkpoint_id": f"cp-{i}", "checkpoint": {"id": f"cp-{i}"}})

    assert len(raw._data["thread-compact"]) <= 3
    latest = await repo.get_latest("thread-compact")
    assert latest["checkpoint_id"] == "cp-6"


@pytest.mark.asyncio
async def test_recovery_raises_when_only_corrupt_checkpoints_exist():
    raw = InMemoryCheckpointRepository()
    repo = ResilientCheckpointRepository(raw, compact_every=100, keep_last=10, recovery_scan_limit=5)

    await repo.put("thread-bad", {"checkpoint_id": "bad", "checkpoint": {"id": "bad", "value": 1}})
    raw._data["thread-bad"][-1]["payload"]["checkpoint"]["value"] = 2

    with pytest.raises(CheckpointRecoveryError):
        await repo.get_latest("thread-bad")
