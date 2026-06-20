import pytest
from agent_framework.cache.cache import DistributedCache, InMemoryCache


@pytest.mark.asyncio
async def test_distributed_cache_populates_l1_from_l2():
    l1 = InMemoryCache(); l2 = InMemoryCache()
    await l2.set("k", {"v": 1})
    cache = DistributedCache(l1, l2)
    assert await cache.get("k") == {"v": 1}
    await l2.delete("k")
    assert await cache.get("k") == {"v": 1}
