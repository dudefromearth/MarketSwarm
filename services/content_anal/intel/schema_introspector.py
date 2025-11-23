#!/usr/bin/env python3
"""
schema_introspector.py — Adaptive schema learner for content_anal

Purpose:
  Inspect real enriched items coming from vexy:intake and infer a stable,
  union-based schema for each category. This allows content_anal to remain
  schema-flexible and adapt automatically if upstream RSSAgg changes fields.

Design:
  • Maintain a rolling union of keys per category
  • Track field types (string, list, dict, number) using simple heuristics
  • Expose a stable `infer_schema(items)` function used by orchestrator
  • Optionally store learned schemas in Redis for reuse

This module avoids strict validation — its goal is to mirror, not enforce.
"""

from collections import defaultdict
from typing import List, Dict, Any
import json


# ------------------------------------------------------------
# Basic type classifier
# ------------------------------------------------------------
def classify_type(value: Any) -> str:
    """Return a simple string describing the type of a field.
    Avoids over-engineering — just enough to guide synthetic output.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "unknown"


# ------------------------------------------------------------
# Infer schema from a set of items
# ------------------------------------------------------------
def infer_schema(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a union schema from all observed keys in real content.

    Example:
      Input items:
        {"uid":..., "title":..., "body":..., "categories":[...]}
        {"uid":..., "title":..., "summary":..., "tags":[...]}

      Output schema:
        {
          "uid": {"types": ["string"]},
          "title": {"types": ["string"]},
          "body": {"types": ["string"], "optional": true},
          "categories": {"types": ["list"]},
          "summary": {"types": ["string"], "optional": true},
          "tags": {"types": ["list"], "optional": true}
        }
    """

    if not items:
        return {}

    schema = defaultdict(lambda: {"types": set(), "optional": False})
    total_items = len(items)
    key_counts = defaultdict(int)

    # Examine each item
    for it in items:
        for key, value in it.items():
            key_counts[key] += 1
            schema[key]["types"].add(classify_type(value))

    # Finalize schema
    finalized = {}
    for key, meta in schema.items():
        count = key_counts[key]
        finalized[key] = {
            "types": sorted(list(meta["types"])),
            "optional": (count < total_items)  # optional if not in all items
        }

    return finalized


# ------------------------------------------------------------
# Convenience: merge schema from stored + new items
# ------------------------------------------------------------
def merge_schemas(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine two schemas (useful when caching category schemas).
    """
    merged = {}
    keys = set(old.keys()) | set(new.keys())

    for k in keys:
        old_meta = old.get(k, {"types": [], "optional": True})
        new_meta = new.get(k, {"types": [], "optional": True})

        merged[k] = {
            "types": sorted(list(set(old_meta["types"]) | set(new_meta["types"]))),
            "optional": old_meta.get("optional", True) or new_meta.get("optional", True)
        }

    return merged


# ------------------------------------------------------------
# Optional: store schema per-category in Redis for reuse
# ------------------------------------------------------------
def store_schema(r_intel, category: str, schema: Dict[str, Any]):
    key = f"content_anal:schema:{category}"
    r_intel.set(key, json.dumps(schema))


def load_schema(r_intel, category: str) -> Dict[str, Any]:
    key = f"content_anal:schema:{category}"
    raw = r_intel.get(key)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ------------------------------------------------------------
# High-level wrapper for orchestrator
# ------------------------------------------------------------
def introspect_and_update_schema(r_intel, category: str, items: List[Dict[str, Any]]):
    """
    Load any known schema, merge with the schema inferred from new items,
    and store back into Redis.
    """
    existing = load_schema(r_intel, category)
    observed = infer_schema(items)
    merged = merge_schemas(existing, observed)
    store_schema(r_intel, category, merged)
    return merged
