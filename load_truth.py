#!/usr/bin/env python3
import os, sys, json, time, argparse, redis

def read_json_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"ERROR: file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: invalid JSON in {path}: {e}")

def merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Load merged truth into Redis (single key).")
    p.add_argument("--redis-url",
                   default=os.getenv("BOOTSTRAP_REDIS_URL", "redis://main-redis:6379"))
    # No defaults for file paths — must be provided via CLI or env.
    p.add_argument("--truth",   default=os.getenv("TRUTH_FILE"))
    p.add_argument("--secrets", default=os.getenv("TRUTH_SECRETS_FILE"))
    p.add_argument("--key",     default=os.getenv("TRUTH_REDIS_KEY", "truth:doc"))
    args = p.parse_args(argv)

    if not args.truth:
        sys.exit("ERROR: truth path is required (set --truth or TRUTH_FILE).")

    base = read_json_file(args.truth)
    if args.secrets:
        if os.path.exists(args.secrets):
            base = merge(base, read_json_file(args.secrets))
        else:
            sys.exit(f"ERROR: secrets file not found: {args.secrets}")

    r = redis.Redis.from_url(args.redis_url, decode_responses=True)
    pipe = r.pipeline()
    pipe.set(args.key, json.dumps(base, separators=(",", ":")))
    pipe.set("truth:version", str(base.get("version", "")))
    pipe.set("truth:ts", str(int(time.time())))
    pipe.execute()

    # No file paths or contents echoed—just confirmation.
    print(f"Loaded truth into {args.key} at {args.redis_url}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())