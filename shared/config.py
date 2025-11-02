# shared/config.py
from __future__ import annotations
import os, json, redis

def _env(k, d=None):
    v = os.getenv(k)
    return v if v and v.strip() else d

def _r():
    url = _env("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379")
    return redis.Redis.from_url(url, decode_responses=True)

def load_truth(r=None) -> dict:
    r = r or _r()
    raw = r.get("truth:doc")
    return json.loads(raw) if raw else {}

def resolve_service_context(service_id: str | None = None) -> dict:
    """
    Returns: {
      'service_id', 'component', 'secret_scope',
      'core', 'component_cfg', 'secrets'
    }
    """
    r = _r()
    sid = service_id or _env("SERVICE_ID")
    if not sid:
        raise RuntimeError("SERVICE_ID not set")

    T = load_truth(r)
    comps = (T.get("components") or {})
    secs  = (T.get("secrets") or {})
    core  = (T.get("core") or {})

    # 1) ask registry
    reg_key = f"svc:cfg:{sid}"
    component = r.hget(reg_key, "component")
    secret_scope = r.hget(reg_key, "secret_scope")

    # 2) fallback: if component absent, try component == service_id
    if not component and sid in comps:
        component = sid

    if not component:
        available = ", ".join(sorted(comps.keys()))
        raise RuntimeError(
            f"Service '{sid}' not registered and no matching component.\n"
            f"Register it: svc:cfg:{sid} component=<one of [{available}]>"
        )

    if not secret_scope:
        secret_scope = component

    return {
        "service_id": sid,
        "component": component,
        "secret_scope": secret_scope,
        "core": core,
        "component_cfg": comps.get(component, {}),
        "secrets": secs.get(secret_scope, {}),
    }