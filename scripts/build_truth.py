#!/usr/bin/env python3
"""
MarketSwarm Truth Builder

Location:
  ${ROOT}/scripts/build_truth.py

Conventions:
  - Node definitions (data):      ${ROOT}/truth/*.json          (at least one valid node)
  - Component definitions:        ${ROOT}/truth/components/<name>.json
  - Node schema:                  ${ROOT}/truth/schema/node.json
  - Component schema:             ${ROOT}/truth/schema/component.json
  - Output composite Truth:       ${ROOT}/scripts/truth.json

CLI Modes:
  - No args              -> Build composite Truth (default)
  - check-node           -> Validate a node definition against node schema
  - check-component      -> Validate a component definition against component schema
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import jsonschema

# -------------------------------------------------------------------
# Paths (ROOT is parent of scripts/)
# -------------------------------------------------------------------
SCRIPTS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))

TRUTH_DIR = os.path.join(ROOT, "truth")
COMPONENTS_DIR = os.path.join(TRUTH_DIR, "components")
SCHEMA_DIR = os.path.join(TRUTH_DIR, "schema")

NODE_SCHEMA_PATH = os.path.join(SCHEMA_DIR, "node.json")
COMPONENT_SCHEMA_PATH = os.path.join(SCHEMA_DIR, "component.json")

OUTPUT_TRUTH_PATH = os.path.join(SCRIPTS_DIR, "truth.json")


def load_json(path: str) -> Dict[str, Any]:
    """Load a JSON file or exit with a clear error."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[build_truth] ERROR: Missing file: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[build_truth] ERROR: Invalid JSON in {path}: {e}")
        sys.exit(1)


def find_node_definitions(node_schema: Dict[str, Any]) -> List[str]:
    """
    Scan TRUTH_DIR for candidate node definition JSON files and
    return the ones that validate against the node schema.
    """
    candidates: List[str] = []

    for entry in os.listdir(TRUTH_DIR):
        full = os.path.join(TRUTH_DIR, entry)

        # Skip dirs, schema/, components/, and the output truth.json if present
        if os.path.isdir(full):
            continue
        if not entry.endswith(".json"):
            continue
        if entry == "truth.json":
            continue  # composite output, not a node def

        # Try to load and validate as a node definition
        try:
            data = load_json(full)
            jsonschema.validate(instance=data, schema=node_schema)
        except jsonschema.ValidationError:
            # Not a node definition; ignore
            continue

        candidates.append(full)

    return candidates


def verify_access_points(components: Dict[str, Any]) -> None:
    """
    Ensure that every subscribe_to (bus, key) has at least one matching publish_to (bus, key).
    """
    publishers = set()           # (bus, key)
    subscribers: List[Tuple[str, str, str]] = []  # (component_name, bus, key)

    for name, comp in components.items():
        ap = comp.get("access_points", {})

        for pub in ap.get("publish_to", []):
            bus = pub.get("bus")
            key = pub.get("key")
            if bus and key:
                publishers.add((bus, key))

        for sub in ap.get("subscribe_to", []):
            bus = sub.get("bus")
            key = sub.get("key")
            if bus and key:
                subscribers.append((name, bus, key))

    dangling: List[Tuple[str, str, str]] = []
    for comp_name, bus, key in subscribers:
        if (bus, key) not in publishers:
            dangling.append((comp_name, bus, key))

    if dangling:
        print("[build_truth] ERROR: Dangling subscriptions detected (no publisher found):")
        for comp_name, bus, key in dangling:
            print(f"  - component={comp_name}, bus={bus}, key={key}")
        sys.exit(1)


def verify_models(components: Dict[str, Any]) -> None:
    """
    Ensure that every consumed model has at least one producer.
    Models are declared as objects: { "bus": "...", "key": "..." }.
    """
    produced = set()  # (bus, key)
    consumed: List[Tuple[str, str, str]] = []  # (component_name, bus, key)

    for name, comp in components.items():
        models = comp.get("models", {})

        for m in models.get("produces", []):
            if not isinstance(m, dict):
                continue
            bus = m.get("bus")
            key = m.get("key")
            if bus and key:
                produced.add((bus, key))

        for m in models.get("consumes", []):
            if not isinstance(m, dict):
                continue
            bus = m.get("bus")
            key = m.get("key")
            if bus and key:
                consumed.append((name, bus, key))

    dangling: List[Tuple[str, str, str]] = []
    for comp_name, bus, key in consumed:
        if (bus, key) not in produced:
            dangling.append((comp_name, bus, key))

    if dangling:
        print("[build_truth] ERROR: Dangling model consumptions detected (no producer found):")
        for comp_name, bus, key in dangling:
            print(f"  - component={comp_name}, model_bus={bus}, model_key={key}")
        sys.exit(1)


def build_truth() -> None:
    print(f"[build_truth] ROOT={ROOT}")
    print(f"[build_truth] TRUTH_DIR={TRUTH_DIR}")
    print(f"[build_truth] Components dir: {COMPONENTS_DIR}")
    print(f"[build_truth] Node schema:    {NODE_SCHEMA_PATH}")
    print(f"[build_truth] Comp schema:    {COMPONENT_SCHEMA_PATH}")
    print(f"[build_truth] Output:         {OUTPUT_TRUTH_PATH}")
    print("")

    # Load schemas
    node_schema = load_json(NODE_SCHEMA_PATH)
    component_schema = load_json(COMPONENT_SCHEMA_PATH)

    # Discover node definition(s)
    node_paths = find_node_definitions(node_schema)

    if not node_paths:
        print(
            "[build_truth] ERROR: No valid node definition found in truth/ "
            "(expected at least one JSON matching node schema)."
        )
        sys.exit(1)

    if len(node_paths) > 1:
        print("[build_truth] ERROR: Multiple valid node definitions found:")
        for p in node_paths:
            print(f"  - {p}")
        print(
            "Please keep exactly one active node definition in truth/ "
            "or introduce selection logic/env var if you want multi-node support."
        )
        sys.exit(1)

    node_path = node_paths[0]
    print(f"[build_truth] Using node definition: {node_path}")

    # Load the chosen node definition
    node_def = load_json(node_path)

    # Extract core fields
    version = node_def.get("version", "1.0")
    description = node_def.get("description", "")
    node_info = node_def.get("node", {})
    buses = node_def.get("buses", {})
    # domain is optional now; can be empty if you don't use it
    domain = node_def.get("domain", {})
    component_names = node_def.get("components", [])

    if not isinstance(component_names, list):
        print("[build_truth] ERROR: 'components' in node definition must be a list of names.")
        sys.exit(1)

    # Load and validate each component
    components_out: Dict[str, Any] = {}

    for name in component_names:
        comp_path = os.path.join(COMPONENTS_DIR, f"{name}.json")
        print(f"[build_truth] Loading component '{name}' from {comp_path}")
        comp_def = load_json(comp_path)

        try:
            jsonschema.validate(instance=comp_def, schema=component_schema)
        except jsonschema.ValidationError as e:
            print(f"[build_truth] ERROR: component '{name}' failed schema validation:")
            print(f"  file:    {comp_path}")
            print(f"  path:    {'/'.join(str(p) for p in e.path)}")
            print(f"  message: {e.message}")
            sys.exit(1)

        # Enforce id ↔ node.components binding
        comp_id = comp_def.get("id")
        if comp_id != name:
            print(f"[build_truth] ERROR: component ID mismatch for '{name}':")
            print(f"  node.components entry: '{name}'")
            print(f"  component.id:          '{comp_id}'")
            print("  The component 'id' must match the name used in node.components and filename.")
            sys.exit(1)

        components_out[name] = comp_def

    # Enforce wiring invariants:
    # 1) Every subscription has at least one publisher
    # 2) Every consumed model has at least one producer
    verify_access_points(components_out)
    verify_models(components_out)

    # Compose final Truth in the shape all services already expect
    composite: Dict[str, Any] = {
        "version": version,
        "description": description,
        "node": node_info,
        "buses": buses,
        "domain": domain,
        "components": components_out,
    }

    os.makedirs(os.path.dirname(OUTPUT_TRUTH_PATH), exist_ok=True)
    with open(OUTPUT_TRUTH_PATH, "w") as f:
        json.dump(composite, f, indent=2)

    print("")
    print(f"[build_truth] ✅ Wrote composite Truth to {OUTPUT_TRUTH_PATH}")


# -------------------------------------------------------------------
# Single-node / single-component validators
# -------------------------------------------------------------------

def check_node(node_path: str) -> None:
    """Validate a single node definition against the node schema."""
    print(f"[build_truth] Checking node definition: {node_path}")
    node_schema = load_json(NODE_SCHEMA_PATH)
    data = load_json(node_path)

    try:
        jsonschema.validate(instance=data, schema=node_schema)
    except jsonschema.ValidationError as e:
        print("[build_truth] ❌ Node validation failed")
        print(f"  file:    {node_path}")
        print(f"  path:    {'/'.join(str(p) for p in e.path)}")
        print(f"  message: {e.message}")
        sys.exit(1)

    print("[build_truth] ✅ Node definition is valid according to schema")


def check_component(name: str = "", file_path: str = "") -> None:
    """
    Validate a single component definition against the component schema.

    You can pass either:
      - a component name (looked up in truth/components/<name>.json), or
      - a direct file path.
    """
    if not file_path and not name:
        print("[build_truth] ERROR: check-component requires either --name or --file")
        sys.exit(1)

    if not file_path:
        file_path = os.path.join(COMPONENTS_DIR, f"{name}.json")

    print(f"[build_truth] Checking component definition: {file_path}")
    component_schema = load_json(COMPONENT_SCHEMA_PATH)
    data = load_json(file_path)

    try:
        jsonschema.validate(instance=data, schema=component_schema)
    except jsonschema.ValidationError as e:
        print("[build_truth] ❌ Component validation failed")
        print(f"  file:    {file_path}")
        print(f"  path:    {'/'.join(str(p) for p in e.path)}")
        print(f"  message: {e.message}")
        sys.exit(1)

    print("[build_truth] ✅ Component definition is valid according to schema")


# -------------------------------------------------------------------
# CLI entrypoint
# -------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MarketSwarm Truth Builder and Validator"
    )

    subparsers = parser.add_subparsers(dest="command")

    # Default (no subcommand) -> build_truth()

    # check-node
    pn = subparsers.add_parser("check-node", help="Validate a node definition JSON")
    pn.add_argument(
        "--file",
        "-f",
        required=True,
        help="Path to node definition JSON file (e.g., truth/mm_node.json)",
    )

    # check-component
    pc = subparsers.add_parser("check-component", help="Validate a component JSON")
    group = pc.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--name",
        "-n",
        help="Component name (expects truth/components/<name>.json)",
    )
    group.add_argument(
        "--file",
        "-f",
        help="Path to a component JSON file",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.command == "check-node":
        check_node(args.file)
    elif args.command == "check-component":
        check_component(name=getattr(args, "name", ""), file_path=getattr(args, "file", ""))
    else:
        # Default: build composite Truth
        build_truth()