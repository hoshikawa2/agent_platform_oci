from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any


class RateLimitExceeded(RuntimeError):
    pass


class InMemoryRateLimiter:
    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, *, tenant_id: str, agent_id: str | None, channel: str | None) -> None:
        default_limit = ((self.config.get("default") or {}).get("requests_per_minute")) or 600
        agent_limits = self.config.get("agents") or {}
        channel_limits = self.config.get("channels") or {}

        limit = default_limit
        if agent_id and agent_id in agent_limits:
            limit = agent_limits[agent_id].get("requests_per_minute", limit)
        if channel and channel in channel_limits:
            limit = min(limit, channel_limits[channel].get("requests_per_minute", limit))

        key = f"{tenant_id}:{agent_id or '*'}:{channel or '*'}"
        now = time.time()
        bucket = self.events[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= int(limit):
            raise RateLimitExceeded(f"Gateway rate limit exceeded for {key}: {limit}/min")
        bucket.append(now)
