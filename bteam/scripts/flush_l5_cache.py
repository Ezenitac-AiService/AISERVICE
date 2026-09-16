"""
Targeted L5 cache invalidation script (T035 / US3 / FR-009).
Executes SCAN 0 MATCH olliview:l5:* COUNT 100 and deletes all matching keys
to invalidate stale legacy cache entries upon model upgrade.
"""

import os
import sys
import redis
from typing import Optional


def flush_l5_cache_keys(redis_client: Optional[redis.Redis] = None, host: str = "redis", port: int = 6379) -> int:
    """Scans for 'olliview:l5:*' keys with SCAN COUNT 100 and purges them atomically."""
    if redis_client is None:
        redis_host = os.getenv("REDIS_HOST", host)
        redis_port = int(os.getenv("REDIS_PORT", port))
        redis_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=5.0)

    cursor = 0
    total_deleted = 0

    while True:
        cursor, keys = redis_client.scan(cursor=cursor, match="olliview:l5:*", count=100)
        if keys:
            redis_client.delete(*keys)
            total_deleted += len(keys)
        if cursor == 0 or cursor == "0" or cursor == b"0":
            break

    print(f"[FlushL5Cache] Invalidation complete. Purged {total_deleted} keys matching 'olliview:l5:*'.")
    return total_deleted


if __name__ == "__main__":
    count = flush_l5_cache_keys()
    print(f"Successfully flushed {count} L5 cache keys.")
