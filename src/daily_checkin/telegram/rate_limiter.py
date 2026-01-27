from __future__ import annotations

import time
from redis import Redis


class RateLimiter:
    def __init__(self, redis: Redis, rate_per_sec: int):
        self.redis = redis
        self.rate = rate_per_sec

    def allow(self, key: str) -> bool:
        now = int(time.time())
        bucket = f"tg_rate:{key}:{now}"
        count = self.redis.incr(bucket)
        if count == 1:
            self.redis.expire(bucket, 2)
        return count <= self.rate