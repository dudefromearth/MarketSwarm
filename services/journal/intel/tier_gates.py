"""
Tier gate enforcement for Journal service.
Reads tier_gates config from Redis with caching.
"""
import json
import time
import redis

_cache = None
_cache_ts = 0
_CACHE_TTL = 30  # seconds


def _load_config():
    """Load tier_gates from Redis with 30s cache."""
    global _cache, _cache_ts
    now = time.time()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache
    try:
        r = redis.Redis(host='127.0.0.1', port=6379, socket_timeout=2, decode_responses=True)
        raw = r.get('tier_gates')
        if raw:
            _cache = json.loads(raw)
            _cache_ts = now
        r.close()
    except Exception:
        pass
    return _cache


def get_gate_limit(tier, feature_key):
    """
    Get the numeric limit for a feature and tier.
    Returns None if no limit applies (full_production mode, unknown feature, admin tier).
    Returns -1 for unlimited.
    Returns a positive int for the actual limit.
    """
    config = _load_config()
    if not config or config.get('mode') == 'full_production':
        return None

    # Admin/coaching always bypass
    tier_lower = tier.lower() if tier else 'observer'
    if tier_lower in ('administrator', 'coaching'):
        return None

    # Check tier override first, then default
    tier_overrides = config.get('tiers', {}).get(tier_lower, {})
    if feature_key in tier_overrides:
        return tier_overrides[feature_key]

    # Fall back to defaults
    defaults = config.get('defaults', {})
    feature_def = defaults.get(feature_key)
    if not feature_def:
        return None

    return feature_def.get('value')


def get_user_tier(request):
    """Extract user tier from X-User-Tier header."""
    return request.headers.get('X-User-Tier', 'observer')
