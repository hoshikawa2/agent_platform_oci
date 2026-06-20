import asyncio
import pytest
from agent_framework.cache.cache import InMemoryCache, DistributedCache

@pytest.mark.asyncio
async def test_in_memory_cache_ttl_expires():
    cache = InMemoryCache()
    await cache.set('k', {'v': 1}, ttl_seconds=1)
    assert await cache.get('k') == {'v': 1}
    await asyncio.sleep(1.05)
    assert await cache.get('k') is None

@pytest.mark.asyncio
async def test_distributed_cache_promotes_l2_to_l1():
    l1, l2 = InMemoryCache(), InMemoryCache()
    cache = DistributedCache(l1, l2)
    await l2.set('x', 'from-l2')
    assert await cache.get('x') == 'from-l2'
    assert await l1.get('x') == 'from-l2'
