#!/usr/bin/env python3
import os
import redis
import json

def setup_service_environment(svc: str):
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    truth_raw = r.get("truth")
    if not truth_raw:
        raise RuntimeError("truth not found in system-redis")
    truth = json.loads(truth_raw)

    comp = truth["components"].get(svc)
    if not comp:
        raise RuntimeError(f"No component block for {svc}")

    print(f"[{svc}] Setup complete — truth loaded")
    return {"truth": truth, "component": comp, "redis": r}