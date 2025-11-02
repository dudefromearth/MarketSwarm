#!/usr/bin/env python3
# admin_console.py
from __future__ import annotations
import os, sys, json, argparse, time

# ---------- Redis handle (lazy import so `./admin help` works without deps) ----------
def R(url: str | None = None):
    try:
        import redis  # type: ignore
    except Exception:
        print("Missing dependency 'redis'. Install with: pip install 'redis>=5.0'", file=sys.stderr)
        sys.exit(2)
    url = url or os.getenv("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379")
    return redis.Redis.from_url(url, decode_responses=True)

# ---------- infra ----------
def _json_load(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)

def _merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out

# ---------- commands ----------
def cmd_load_truth(args):
    truth_path = args.truth or os.getenv("TRUTH_FILE")
    if not truth_path:
        sys.exit("ERROR: --truth or TRUTH_FILE is required")
    base = _json_load(truth_path)

    secrets_path = args.secrets or os.getenv("TRUTH_SECRETS_FILE")
    if secrets_path:
        if not os.path.exists(secrets_path):
            sys.exit(f"ERROR: secrets file not found: {secrets_path}")
        base = _merge(base, _json_load(secrets_path))

    r = R(args.redis_url)
    pipe = r.pipeline()
    pipe.set(args.key, json.dumps(base, separators=(",", ":")))
    pipe.set("truth:version", str(base.get("version", "")))
    pipe.set("truth:ts", str(int(time.time())))
    pipe.execute()
    print(f"Loaded {args.key} → {args.redis_url}")

def cmd_components(args):
    r = R(args.redis_url)
    raw = r.get(args.key)
    T = json.loads(raw) if raw else {}
    comps = T.get("components") or {}

    # JSON mode: emit structured component + metadata
    if getattr(args, "json", False):
        out = []
        for key, cfg in comps.items():
            meta = (cfg or {}).get("meta", {})
            out.append({
                "component": key,
                "name": meta.get("name", ""),
                "service_id": meta.get("service_id", ""),
                "description": meta.get("description", "")
            })
        print(json.dumps(out, indent=2))
        return

    # Pretty table (no secrets)
    rows = []
    for key in sorted(comps.keys()):
        meta = (comps[key] or {}).get("meta", {}) or {}
        rows.append((
            key,
            meta.get("name", ""),
            meta.get("service_id", ""),
            meta.get("description", "")
        ))

    # column widths
    w_key  = max([len("component"), *(len(row[0]) for row in rows)] or [9])
    w_name = max([len("name"), *(len(row[1]) for row in rows)] or [4])
    w_sid  = max([len("service_id"), *(len(row[2]) for row in rows)] or [10])

    header = f"{'component'.ljust(w_key)}  {'name'.ljust(w_name)}  {'service_id'.ljust(w_sid)}  description"
    print(header)
    print("-" * len(header))
    for comp, name, sid, desc in rows:
        print(f"{comp.ljust(w_key)}  {name.ljust(w_name)}  {sid.ljust(w_sid)}  {desc}")

def cmd_register(args):
    r = R(args.redis_url)
    sid = args.service_id
    comp = args.component
    sec  = args.secret_scope or comp
    r.sadd("svc:list", sid)
    r.hset(f"svc:cfg:{sid}", mapping={"component": comp, "secret_scope": sec})
    print(f"Registered {sid} -> component={comp} secret_scope={sec}")

def cmd_services(args):
    r = R(args.redis_url)
    sids = sorted(r.smembers("svc:list"))
    for sid in sids:
        h = r.hgetall(f"svc:cfg:{sid}")
        hb = r.get(f"svc:hb:{sid}")
        hb_s = f" last_hb={hb}" if hb else ""
        print(f"{sid}: component={h.get('component')} secret_scope={h.get('secret_scope')}{hb_s}")

def cmd_show(args):
    r = R(args.redis_url)
    sid = args.service_id
    h = r.hgetall(f"svc:cfg:{sid}")
    if not h:
        print(f"{sid}: not registered")
        return
    raw = r.get(args.key)
    T = json.loads(raw) if raw else {}
    comp = h.get("component")
    sec  = h.get("secret_scope") or comp
    comp_cfg = (T.get("components") or {}).get(comp, {})
    sec_keys = sorted(((T.get("secrets") or {}).get(sec, {}) or {}).keys())
    out = {
        "service_id": sid,
        "component": comp,
        "secret_scope": sec,
        "component_cfg": comp_cfg,
        "secret_fields": sec_keys,   # names only; NEVER values
    }
    print(json.dumps(out, indent=2))

def cmd_keys(args):
    r = R(args.redis_url)
    exists = lambda k: "✓" if r.exists(k) else "×"
    sids = sorted(r.smembers("svc:list"))
    print(f"{args.key}: {exists(args.key)} (len={len(r.get(args.key) or '')})")
    print(f"truth:version: {exists('truth:version')} value={r.get('truth:version') or ''}")
    print(f"truth:ts: {exists('truth:ts')} value={r.get('truth:ts') or ''}")
    print(f"svc:list: {exists('svc:list')} count={len(sids)}")
    for sid in sids:
        print(f"  svc:cfg:{sid}: {r.hgetall(f'svc:cfg:{sid}')}")

# ---------- help ----------
TOPIC_HELP = {
    "quickstart": """\
Quickstart
  1) Load truth into Redis:
       admin_console.py load-truth --truth $TRUTH_FILE --secrets $TRUTH_SECRETS_FILE
  2) See available component keys:
       admin_console.py components
  3) Map services to components (self-discovery):
       admin_console.py register --service-id rss_agg --component rss_agg
       admin_console.py register --service-id massive --component massive
  4) Start services with SERVICE_ID + BOOTSTRAP_REDIS_URL set.
""",
    "load-truth": """\
load-truth
  Merge truth + (optional) secrets and store at truth:doc (plus truth:version, truth:ts).
  Args:
    --truth   PATH   (or env TRUTH_FILE)      REQUIRED
    --secrets PATH   (or env TRUTH_SECRETS_FILE) optional
    --redis-url URL  (or env BOOTSTRAP_REDIS_URL) defaults to redis://main-redis:6379
    --key KEY        defaults to truth:doc
  Example:
    admin_console.py load-truth --truth $TRUTH_FILE --secrets $TRUTH_SECRETS_FILE
""",
    "components": """\
components
  List component keys with metadata (name, service_id, description) from truth:doc.
  Examples:
    admin_console.py components
    admin_console.py components --json
""",
    "register": """\
register
  Register or patch a service mapping for self-discovery.
  Fields stored:
    svc:list                   ← adds service_id to set
    svc:cfg:<service_id>:
      - component=<key under truth.components>
      - secret_scope=<key under truth.secrets> (default: component)
  Example:
    admin_console.py register --service-id rss_agg --component rss_agg
""",
    "services": """\
services
  List registered services and their mappings (no secret values).
  Example:
    admin_console.py services
""",
    "show": """\
show
  Show one mapping plus its component config and the names of required secret fields.
  Example:
    admin_console.py show --service-id massive
""",
    "keys": """\
keys
  Inspect existence/basic sizes of admin-related Redis keys (no secrets).
  Example:
    admin_console.py keys
""",
    "env": """\
Environment variables
  BOOTSTRAP_REDIS_URL   Redis URL for admin + services
  TRUTH_FILE            Absolute path to truth.json (not in repo)
  TRUTH_SECRETS_FILE    Absolute path to truth_secrets.json (gitignored)
  TRUTH_REDIS_KEY       Redis key to store merged truth (default: truth:doc)
  SERVICE_ID            Service-provided identity used for self-discovery
""",
}

def cmd_help(args):
    topic = (args.topic or "").strip().lower()
    if topic and topic in TOPIC_HELP:
        print(TOPIC_HELP[topic]); return
    # default: print compact index + quickstart
    print("admin_console — MarketSwarm admin")
    print()
    print("Commands:")
    print("  load-truth   Merge truth(+secrets) → truth:doc")
    print("  components   List component keys in truth")
    print("  register     Map service_id → component (+secret_scope)")
    print("  services     List registered services")
    print("  show         Show one mapping + cfg, secret field names only")
    print("  keys         Inspect admin keys (existence/counts)")
    print("  help [topic] Show help (topics: quickstart, env, load-truth, components, register, services, show, keys)")
    print()
    print(TOPIC_HELP["quickstart"])

# ---------- main ----------
def main():
    p = argparse.ArgumentParser(prog="admin_console", description="MarketSwarm admin console")
    p.add_argument("--redis-url", default=os.getenv("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379"))
    p.add_argument("--key", default=os.getenv("TRUTH_REDIS_KEY", "truth:doc"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("help", help="show help (use: help [topic])")
    s.add_argument("topic", nargs="?")
    s.set_defaults(func=cmd_help)

    s = sub.add_parser("load-truth", help="merge + store truth into Redis")
    s.add_argument("--truth")
    s.add_argument("--secrets")
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

if __name__ == "__main__":
    main()