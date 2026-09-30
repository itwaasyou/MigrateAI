import os
import time

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

redis_client = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    socket_connect_timeout=1,
    socket_timeout=1,
    decode_responses=True,
)
memory_counters: dict[str, tuple[float, int]] = {}
INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def enforce_rate_limit(request: Request, key: str, limit: int, seconds: int) -> None:
    client_ip = request.client.host if request.client else "unknown"
    counter_key = f"migrateai:limit:{key}:{client_ip}"
    if os.getenv("APP_ENV", "development") != "production":
        now = time.monotonic()
        started, count = memory_counters.get(counter_key, (now, 0))
        if now - started >= seconds:
            started, count = now, 0
        count += 1
        memory_counters[counter_key] = (started, count)
        if count > limit:
            raise HTTPException(429, "Too many requests. Wait briefly and try again.")
        return
    try:
        count = int(redis_client.eval(INCREMENT_WINDOW, 1, counter_key, seconds))
    except RedisError as exc:
        raise HTTPException(
            503, "Rate limiting service is unavailable. Retry shortly."
        ) from exc
    if count > limit:
        raise HTTPException(429, "Too many requests. Wait briefly and try again.")
