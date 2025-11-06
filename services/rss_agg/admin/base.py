import os, sys, redis

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v

def R(url: str | None = None):
    """Centralized Redis connection helper"""
    url = url or _env("REDIS_URL", "redis://localhost:6379")
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        print(f"Redis connect failed: {url} ({e})", file=sys.stderr)
        sys.exit(1)