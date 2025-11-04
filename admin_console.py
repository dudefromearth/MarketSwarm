#!/usr/bin/env python3
# admin_console.py
from __future__ import annotations
import os, sys, json, argparse, time

# ---------- TOPIC_HELP (Added – Unresolved Fix) ----------
TOPIC_HELP = {
    "quickstart": """
Quickstart:
  ./admin setup  # Setup local .venv
  ./admin load-truth --truth /path/to/truth.json  # Load/replace truth
  ./admin components --json  # List components
  ./admin register --service-id rss_agg --component rss_agg  # Map service
""",
    "env": """
Env Vars:
  THE_TRUTH: Path to truth.json (default: truth.json)
  BOOTSTRAP_REDIS_URL: Redis URL (default: redis://main-redis:6379)
  TRUTH_REDIS_KEY: Key for truth (default: truth:doc)
""",
    "load-truth": """
load-truth [--truth <path>]:
  Load/replace truth into Redis key. Path from --truth, THE_TRUTH, or default root/truth.json.
  Replaces old completely (DEL + SET).
""",
    "components": """
components [--json]:
  List components from truth.
""",
    "register": """
register --service-id <id> --component <comp> [--secret-scope <scope>]:
  Map service to component (+secret scope).
""",
    "services": """
services:
  List registered services.
""",
    "show": """
show --service-id <id>:
  Show mapping + cfg for a service (no secret values).
""",
    "keys": """
keys:
  Inspect admin keys (existence/counts).
"""
}

# ---------- Redis handle ----------
def R(url: str | None = None):
    try:
        import redis
    except Exception:
        print("Missing dependency 'redis'. Install with: pip install 'redis>=5.0'", file=sys.stderr)
        sys.exit(2)
    url = url or os.getenv("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379")
    return redis.Redis.from_url(url, decode_responses=True)

# ---------- infra ----------
def _json_load(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)

# ---------- commands ----------
def cmd_load_truth(args):
    truth_path = args.truth or os.getenv("THE_TRUTH") or "truth.json"
    if not truth_path or not os.path.exists(truth_path):
        sys.exit(f"ERROR: Truth path not found: {truth_path}")
    truth = _json_load(truth_path)

    r = R(args.redis_url)
    pipe = r.pipeline()
    pipe.delete(args.key)  # Replace old completely
    pipe.set(args.key, json.dumps(truth, separators=(",", ":")))
    pipe.set("truth:version", str(truth.get("version", "")))
    pipe.set("truth:ts", str(int(time.time())))
    pipe.execute()
    print(f"Loaded {args.key} → {args.redis_url}")

def cmd_components(args):
    r = R(args.redis_url)
    raw = r.get(args.key)
    T = json.loads(raw) if raw else {}
    comps = T.get("components") or {}

    if getattr(args, "json", False):
        out = []
        for key, comp in comps.items():
            out.append({
                "component": key,
                "meta": comp.get("meta", {}),
                "access_points": comp.get("access_points", {})
            })
        print(json.dumps(out, indent=2))
        return

    print("Components:")
    for key, comp in comps.items():
        print(f"  {key}:")
        print(f"    meta: {comp.get('meta', {}).get('name', 'unnamed')}")
        print(f"    access_points: {comp.get('access_points', {})}")

def cmd_register(args):
    r = R(args.redis_url)
    comp = r.hget(f"svc:cfg:{args.service_id}", "component")
    if comp:
        print(f"Already registered {args.service_id} → {comp}")
        return
    r.hset(f"svc:cfg:{args.service_id}", "component", args.component)
    if args.secret_scope:
        r.hset(f"svc:cfg:{args.service_id}", "secret_scope", args.secret_scope)
    print(f"Registered {args.service_id} → {args.component}")

def cmd_services(args):
    r = R(args.redis_url)
    services = r.keys("svc:cfg:*")
    print("Services:")
    for svc in services:
        svc_id = svc.replace("svc:cfg:", "")
        comp = r.hget(svc, "component")
        print(f"  {svc_id} → {comp or 'unmapped'}")

def cmd_show(args):
    r = R(args.redis_url)
    comp = r.hget(f"svc:cfg:{args.service_id}", "component")
    if not comp:
        print(f"Service {args.service_id} not registered")
        return
    print(f"Service {args.service_id}:")
    print(f"  Component: {comp}")
    print(f"  Secret scope: {r.hget(f"svc:cfg:{args.service_id}", "secret_scope") or 'none'}")

def cmd_keys(args):
    r = R(args.redis_url)
    keys = r.keys("*")
    print("Admin keys:")
    for k in keys:
        if k.startswith("truth:") or k.startswith("svc:"):
            count = 0
            if r.type(k) == b'set':
                count = r.scard(k)
            elif r.type(k) == b'zset':
                count = r.zcard(k)
            elif r.type(k) == b'stream':
                count = r.xlen(k)
            print(f"  {k}: {r.type(k).decode()} (count: {count})")

def cmd_help(args):
    print("MarketSwarm admin_console.py")
    print("Commands:")
    print("  load-truth [--truth <path>] Load/replace truth to Redis key")
    print("  components [--json] List components from truth")
    print("  register --service-id <id> --component <comp> [--secret-scope <scope>] Map service to component")
    print("  services List registered services")
    print("  show --service-id <id> Show service mapping + cfg")
    print("  keys Inspect admin keys (existence/counts)")
    print("  help [topic] Show help (topics: quickstart, env, load-truth, components, register, services, show, keys)")
    print()
    if args.topic:
        topic = args.topic
        if topic in TOPIC_HELP:
            print(TOPIC_HELP[topic])
        else:
            print("Topic not found. Available: quickstart, env, load-truth, components, register, services, show, keys")
    else:
        print(TOPIC_HELP["quickstart"])

if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="admin_console", description="MarketSwarm admin console")
    p.add_argument("--redis-url", default=os.getenv("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379"))
    p.add_argument("--key", default=os.getenv("TRUTH_REDIS_KEY", "truth:doc"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("help", help="show help (use: help [topic])")
    s.add_argument("topic", nargs="?")
    s.set_defaults(func=cmd_help)

    s = sub.add_parser("load-truth", help="load/replace truth into Redis")
    s.add_argument("--truth", help="Path to truth.json (or use THE_TRUTH env)")
    s.set_defaults(func=cmd_load_truth)

    s = sub.add_parser("components", help="list component keys + metadata")
    s.add_argument("--json", action="store_true", help="output as JSON")
    s.set_defaults(func=cmd_components)

    s = sub.add_parser("register", help="map a service to a component (+secret scope)")
    s.add_argument("--service-id", required=True)
    s.add_argument("--component", required=True)
    s.add_argument("--secret-scope")
    s.set_defaults(func=cmd_register)

    s = sub.add_parser("services", help="list registered services")
    s.set_defaults(func=cmd_services)

    s = sub.add_parser("show", help="show mapping + cfg for a service (no secret values)")
    s.add_argument("--service-id", required=True)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("keys", help="inspect admin keys existence and counts")
    s.set_defaults(func=cmd_keys)

    args = p.parse_args()
    args.func(args)