# Massive Service Scaffold

# setup.py
#!/usr/bin/env python3
"""
setup.py — Massive Service Environment Setup
"""
import redis
import json
import os
from urllib.parse import urlparse

def setup_environment():
    redis_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    p = urlparse(redis_url)
    r_system = redis.Redis(host=p.hostname, port=p.port, decode_responses=True)

    raw_truth = r_system.get("truth")
    truth = json.loads(raw_truth)

    svc = "massive"
    comp = truth["components"][svc]

    return {
        "SERVICE_ID": svc,
        "truth": truth,
        "component": comp,
        "r_system": r_system,
    }



