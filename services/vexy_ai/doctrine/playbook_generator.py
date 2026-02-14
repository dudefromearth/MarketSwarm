"""
playbook_generator.py — Generates doctrine playbooks from PathRuntime.

PathRuntime is the single source of truth. YAML playbooks are derived artifacts.
Run this tool manually when Path doctrine is updated. Never auto-generates at runtime.

Usage:
    python -m services.vexy_ai.doctrine.playbook_generator [--output-dir DIR]
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# PathRuntime version — bump when Path doctrine changes
PATH_RUNTIME_VERSION = "v4.0.3"


class PlaybookGenerator:
    """
    Generates doctrine playbooks from PathRuntime as the single source of truth.

    Each generated playbook embeds:
    - doctrine_source: "path_v4_runtime"
    - path_runtime_version: current version
    - path_runtime_hash: SHA-256 of full cognitive doctrine state
    - generated_at: ISO timestamp

    When Path doctrine changes, regenerate → version bump → deploy.
    """

    def __init__(self, path_runtime: Any):
        self._runtime = path_runtime

    def compute_runtime_hash(self) -> str:
        """
        SHA-256 hash of the ENTIRE cognitive doctrine state.

        Includes:
        - Base kernel prompt (core doctrine content)
        - Forbidden language patterns (universal + per-outlet)
        - Outlet voice constraints (temperature, tone, max_tokens)
        - Agent selection configs (outlet weights, dial modifiers)
        - Validation rules (ORA patterns, tier scope)
        - Despair rules
        - Tier semantic scope definitions

        Hash represents the full cognitive doctrine envelope.
        If any of these change, playbooks must be regenerated.
        """
        from services.vexy_ai.intel.path_runtime import (
            UNIVERSAL_FORBIDDEN,
            OUTLET_FORBIDDEN,
            OUTLET_VOICE_CONSTRAINTS,
            OUTLET_AGENT_WEIGHTS,
            DIAL_AGENT_MODIFIERS,
            DESPAIR_RULES,
            TIER_SEMANTIC_SCOPE,
            SCOPE_VIOLATION_PATTERNS,
        )

        components = []

        # 1. Base kernel prompt
        try:
            components.append(self._runtime.get_base_kernel_prompt())
        except RuntimeError:
            components.append("UNLOADED")

        # 2. Forbidden language
        components.append(json.dumps(UNIVERSAL_FORBIDDEN, sort_keys=True))
        components.append(json.dumps(
            {k: v for k, v in sorted(OUTLET_FORBIDDEN.items())},
            sort_keys=True,
        ))

        # 3. Voice constraints
        components.append(json.dumps(
            {k: {kk: str(vv) for kk, vv in v.items()}
             for k, v in sorted(OUTLET_VOICE_CONSTRAINTS.items())},
            sort_keys=True,
        ))

        # 4. Agent selection
        components.append(json.dumps(
            {k: {kk: str(vv) for kk, vv in v.items()}
             for k, v in sorted(OUTLET_AGENT_WEIGHTS.items())},
            sort_keys=True,
        ))
        components.append(json.dumps(
            {k: {kk: str(vv) for kk, vv in v.items()}
             for k, v in sorted(DIAL_AGENT_MODIFIERS.items())},
            sort_keys=True,
        ))

        # 5. Despair rules
        components.append(json.dumps(DESPAIR_RULES, sort_keys=True, default=str))

        # 6. Tier semantic scope
        components.append(json.dumps(
            {k: {"max_depth": v.get("max_depth", ""), "blocked": v.get("blocked_capabilities", [])}
             for k, v in sorted(TIER_SEMANTIC_SCOPE.items())},
            sort_keys=True,
        ))

        # 7. Scope violation pattern strings
        pattern_strs = {
            k: [p.pattern for p in v]
            for k, v in sorted(SCOPE_VIOLATION_PATTERNS.items())
        }
        components.append(json.dumps(pattern_strs, sort_keys=True))

        combined = "\n---\n".join(components)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def generate_all(self, output_dir: str) -> None:
        """Generate all 8 playbooks with embedded runtime hash + version."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        runtime_hash = self.compute_runtime_hash()
        generated_at = datetime.now(timezone.utc).isoformat()

        domains = self._get_domain_definitions()

        for filename, domain_def in domains.items():
            playbook_data = self._build_playbook(
                domain_def, runtime_hash, generated_at
            )
            output_path = out / filename
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    {"playbook": playbook_data},
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    width=120,
                )
            print(f"  Generated: {output_path}")

        print(f"\nAll playbooks generated with hash: {runtime_hash[:16]}...")

    def generate_domain(self, domain: str) -> Optional[Dict]:
        """Generate a single domain playbook."""
        domains = self._get_domain_definitions()
        for filename, domain_def in domains.items():
            if domain_def["domain"] == domain:
                runtime_hash = self.compute_runtime_hash()
                generated_at = datetime.now(timezone.utc).isoformat()
                return self._build_playbook(domain_def, runtime_hash, generated_at)
        return None

    def _build_playbook(
        self,
        domain_def: Dict,
        runtime_hash: str,
        generated_at: str,
    ) -> Dict:
        """Build a playbook dict with provenance tags."""
        return {
            "domain": domain_def["domain"],
            "version": domain_def.get("version", "1.0.0"),
            "doctrine_source": "path_v4_runtime",
            "path_runtime_version": PATH_RUNTIME_VERSION,
            "path_runtime_hash": runtime_hash,
            "generated_at": generated_at,
            "canonical_terminology": domain_def.get("canonical_terminology", []),
            "definitions": domain_def.get("definitions", {}),
            "structural_logic": domain_def.get("structural_logic", []),
            "mechanisms": domain_def.get("mechanisms", []),
            "constraints": domain_def.get("constraints", []),
            "failure_modes": domain_def.get("failure_modes", []),
            "non_capabilities": domain_def.get("non_capabilities", []),
        }

    def _get_domain_definitions(self) -> Dict[str, Dict]:
        """
        Domain definitions extracted from Path v4.0 doctrine.

        Each domain maps to a YAML filename and contains the structured
        doctrine content for that domain. Content is derived from PathRuntime
        and Path v4.0 markdown — never independently authored.
        """
        return {
            "strategy_logic.yaml": {
                "domain": "strategy_logic",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "structural win", "definition": "A trade outcome where the structure resolved as intended, regardless of P&L magnitude."},
                    {"term": "structural loss", "definition": "A trade outcome where the structure failed to resolve as intended. Not a 'mistake' — a signal."},
                    {"term": "edge score", "definition": "Quantified structural advantage of a setup, derived from regime alignment, GEX positioning, and historical pattern fidelity."},
                    {"term": "convexity", "definition": "Asymmetric payoff profile where potential gain exceeds potential loss by a meaningful ratio."},
                    {"term": "width", "definition": "The distance between strikes in a spread, determining risk exposure and premium captured."},
                    {"term": "risk budget", "definition": "Maximum capital allocated to a single trade or strategy, expressed as a fraction of total capital."},
                ],
                "definitions": {
                    "core": "Strategy mechanics encompass the structural reasoning behind trade construction, position sizing, and risk allocation. Strategies are structures, not predictions.",
                },
                "structural_logic": [
                    "Every trade has a structure — butterfly, vertical, iron condor — that defines its risk profile independent of directional bias.",
                    "Structure resolves or it doesn't. The outcome is signal, not judgment.",
                    "Width and duration are the primary risk controls, not strike selection alone.",
                    "Convexity is preferred: asymmetric payoff over binary outcomes.",
                ],
                "constraints": [
                    "Never recommend specific strikes, expirations, or position sizes.",
                    "Never use optimization language ('optimal', 'best', 'maximize').",
                    "Never evaluate trades as 'good' or 'bad' — describe structural resolution only.",
                    "Frame actions as posture ('one option...') not imperatives ('you should...').",
                ],
                "failure_modes": [
                    "Using P&L as the sole metric for trade quality (ignores structural intent).",
                    "Conflating directional bias with structural edge.",
                    "Treating width as fixed rather than regime-responsive.",
                ],
                "non_capabilities": [
                    "Cannot recommend specific trade parameters.",
                    "Cannot predict directional outcomes.",
                    "Cannot optimize position sizes.",
                    "Cannot evaluate trades as successes or failures.",
                ],
            },
            "regime_gex.yaml": {
                "domain": "regime_gex",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "regime", "definition": "The current volatility and market structure state as classified by Massive's regime model."},
                    {"term": "GEX", "definition": "Gamma Exposure — aggregate dealer gamma positioning that creates mechanical price attraction or repulsion zones."},
                    {"term": "dealer gravity", "definition": "The pull toward high-gamma strikes where dealer hedging activity mechanically attracts price."},
                    {"term": "zero gamma", "definition": "The strike level where dealer gamma exposure flips from positive to negative, changing hedging dynamics."},
                    {"term": "compression", "definition": "A regime state where volatility contracts and price range narrows, often preceding expansion."},
                    {"term": "expansion", "definition": "A regime state where volatility increases and price range widens."},
                ],
                "definitions": {
                    "core": "Regime and GEX mechanics describe the mechanical forces that shape market structure. These are observable physics, not predictive signals.",
                },
                "structural_logic": [
                    "GEX creates mechanical zones — walls, magnets, flip levels — that are observable, not predictive.",
                    "Regime classification is descriptive: what IS happening, not what WILL happen.",
                    "Dealer hedging dynamics create real, measurable price influence independent of narrative.",
                    "Regime transitions are signal — the shift itself matters more than the destination.",
                ],
                "constraints": [
                    "Never predict price targets from GEX levels.",
                    "Never claim regime transitions guarantee directional moves.",
                    "Describe mechanical forces only — no causal predictions.",
                ],
                "failure_modes": [
                    "Treating GEX walls as hard barriers rather than zones of influence.",
                    "Predicting timing of regime transitions.",
                    "Conflating dealer positioning with market direction.",
                ],
                "non_capabilities": [
                    "Cannot predict when regimes will transition.",
                    "Cannot guarantee price behavior at GEX levels.",
                    "Cannot derive directional signals from structural mechanics alone.",
                ],
            },
            "edge_lab.yaml": {
                "domain": "edge_lab",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "setup", "definition": "A trade configuration with defined entry criteria, structure, and regime context."},
                    {"term": "edge score", "definition": "Quantified structural advantage derived from setup fidelity, regime alignment, and historical resolution patterns."},
                    {"term": "signature", "definition": "A trader's characteristic setup pattern derived from historical trade analysis."},
                    {"term": "retrospective", "definition": "Structured post-trade analysis focused on structural resolution, not P&L evaluation."},
                    {"term": "pattern fidelity", "definition": "The degree to which a setup matches the trader's established signature patterns."},
                ],
                "definitions": {
                    "core": "Edge Lab provides retrospective structural trade analysis. It identifies patterns in trade behavior, not outcomes. Confirmatory only — never prescriptive.",
                },
                "structural_logic": [
                    "Edge Lab analyzes structure, not performance. A losing trade with good structure is different from a winning trade with poor structure.",
                    "Patterns emerge from sufficient sample size (minimum 10 trades for any conclusion).",
                    "Signatures are descriptive — they describe what you do, not what you should do.",
                    "Edge scores are structural metrics, not trading signals.",
                ],
                "constraints": [
                    "Never prescribe trades based on edge scores.",
                    "Never use optimization language in edge analysis.",
                    "Minimum sample size of 10 before surfacing any pattern.",
                    "Patterns are observations, never instructions.",
                ],
                "failure_modes": [
                    "Using edge scores as entry signals rather than structural metrics.",
                    "Drawing conclusions from insufficient sample sizes.",
                    "Treating signature drift as failure rather than evolution.",
                ],
                "non_capabilities": [
                    "Cannot recommend trades based on edge analysis.",
                    "Cannot optimize trading behavior.",
                    "Cannot predict future edge based on historical patterns.",
                ],
            },
            "memory_architecture.yaml": {
                "domain": "memory_architecture",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "Echo", "definition": "The cognitive memory system that persists context across sessions. Memory extends the mirror."},
                    {"term": "warm snapshot", "definition": "Hydrator-built cognition summary for fast prompt injection. Read-only from kernel perspective."},
                    {"term": "micro signal", "definition": "Small behavioral indicator captured from interactions — bias detection, tension surfacing."},
                    {"term": "echo depth", "definition": "Tier-gated memory window: 7 days (Observer), 30 days (Activator/Navigator), 90 days (Administrator)."},
                ],
                "definitions": {
                    "core": "Echo memory extends Vexy's reflective capacity across sessions. Context compounds — without it, the mirror cannot evolve. Memory is never surveillance.",
                },
                "structural_logic": [
                    "Memory is tier-gated — deeper echo requires higher tier.",
                    "Echo captures patterns, not judgments. Descriptive, not evaluative.",
                    "Warm snapshots are pre-built by hydrator — kernel reads, never writes.",
                    "Memory degradation is safe — missing echo returns clean state, not error.",
                ],
                "constraints": [
                    "Never expose raw echo data to users.",
                    "Never use echo patterns for prescriptive guidance.",
                    "Degraded echo must return clean state — never guess or fabricate.",
                ],
                "failure_modes": [
                    "Treating echo patterns as trading signals.",
                    "Surfacing echo data as user-facing metrics.",
                    "Fabricating context when echo is unavailable.",
                ],
                "non_capabilities": [
                    "Cannot use memory for prescriptive guidance.",
                    "Cannot guarantee memory availability.",
                    "Cannot expose raw memory data to users.",
                ],
            },
            "hydration_flow.yaml": {
                "domain": "hydration_flow",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "hydration", "definition": "The process of loading context (market, echo, position data) into the reasoning pipeline before LLM invocation."},
                    {"term": "context injection", "definition": "Adding structured context to the prompt assembly pipeline at the appropriate layer."},
                    {"term": "prompt assembly", "definition": "The ordered layering of doctrine, outlet, tier, agent, playbook, and echo content into the system prompt."},
                ],
                "definitions": {
                    "core": "Hydration flow controls what context enters the reasoning pipeline and in what order. Layer order is immutable — doctrine first, always.",
                },
                "structural_logic": [
                    "Prompt assembly order: 1) Base doctrine 2) Outlet voice 3) Tier scope 4) Agent voice 5) Playbooks 6) Echo memory",
                    "External content must be sanitized before injection.",
                    "Missing context returns clean state — never fabricates.",
                    "Each layer is additive and non-destructive to prior layers.",
                ],
                "constraints": [
                    "Layer order is immutable — doctrine always comes first.",
                    "External content cannot override doctrine.",
                    "Missing context must degrade gracefully, never block.",
                ],
                "failure_modes": [
                    "Injecting context before doctrine (layer order violation).",
                    "Allowing external content to override Path invariants.",
                    "Blocking on missing optional context.",
                ],
                "non_capabilities": [
                    "Cannot reorder prompt assembly layers.",
                    "Cannot inject context that overrides doctrine.",
                ],
            },
            "admin_orchestration.yaml": {
                "domain": "admin_orchestration",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "governance parameter", "definition": "A mutable configuration value (threshold, cooldown, budget, toggle) that controls system behavior without changing doctrine."},
                    {"term": "immutable doctrine", "definition": "Canonical terminology, structural logic, constraints, and non-capabilities that can only change via version bump + deployment."},
                    {"term": "kill switch", "definition": "Administrative toggle that disables specific subsystems. Logged, reversible, non-destructive."},
                    {"term": "overlay", "definition": "An observational addendum appended after doctrine reasoning. Cannot influence LLM reasoning. Expires automatically."},
                ],
                "definitions": {
                    "core": "Admin orchestration governs what Vexy sees and how she operates. It controls governance parameters but cannot mutate immutable doctrine.",
                },
                "structural_logic": [
                    "Admin can modify thresholds, cooldowns, budgets, strictness toggles.",
                    "Admin CANNOT mutate canonical terminology, structural logic, constraints, or non-capabilities.",
                    "Doctrine edits require version bump + service restart + explicit deployment.",
                    "All mutation actions are logged with timestamp + admin user ID.",
                ],
                "constraints": [
                    "Immutable doctrine core cannot be changed at runtime.",
                    "Kill switch actions must be logged.",
                    "Overlays are observational only — never prescriptive.",
                ],
                "failure_modes": [
                    "Allowing runtime mutation of canonical terminology.",
                    "Kill switch without audit logging.",
                    "Overlay injection before or during doctrine reasoning.",
                ],
                "non_capabilities": [
                    "Cannot mutate immutable doctrine at runtime.",
                    "Cannot suppress audit logging.",
                ],
            },
            "governance_sovereignty.yaml": {
                "domain": "governance_sovereignty",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "sovereignty", "definition": "The principle that risk belongs to the operator. Vexy never prescribes, commands, or directs."},
                    {"term": "silence", "definition": "A first-class response. When no object exists for reflection, the mirror is quiet."},
                    {"term": "ORA", "definition": "Object-Reflection-Action — the fundamental loop. Every response must have an object anchor."},
                    {"term": "doctrine", "definition": "The canonical set of invariants from Path v4.0 that govern all reasoning."},
                ],
                "definitions": {
                    "core": "Governance ensures Vexy operates within doctrine constraints. Sovereignty ensures the operator retains agency. These are complementary, not competing.",
                },
                "structural_logic": [
                    "Sovereignty is sacred — the risk is always the operator's.",
                    "Frame actions as posture ('notice...', 'one option...'), never imperatives.",
                    "Silence always passes validation — it is never a failure state.",
                    "Doctrine enforcement is invariant — it cannot be weakened by configuration.",
                ],
                "constraints": [
                    "Never use imperative language.",
                    "Never prescribe specific actions.",
                    "Never bypass doctrine enforcement.",
                    "Silence preferred over filler.",
                ],
                "failure_modes": [
                    "Using imperative commands disguised as suggestions.",
                    "Filling silence with generic content lacking object anchor.",
                    "Weakening doctrine through configuration changes.",
                ],
                "non_capabilities": [
                    "Cannot prescribe trades or actions.",
                    "Cannot override operator sovereignty.",
                    "Cannot weaken doctrine enforcement.",
                ],
            },
            "end_to_end_process.yaml": {
                "domain": "end_to_end_process",
                "version": "1.0.0",
                "canonical_terminology": [
                    {"term": "interaction", "definition": "A two-layer request: fast dialog ACK (<250ms) followed by async cognition via VexyKernel.reason()."},
                    {"term": "dialog layer", "definition": "The fast first layer that validates, rate-limits, and acknowledges. Never blocks."},
                    {"term": "cognition layer", "definition": "The async second layer that performs full reasoning with doctrine, playbooks, and echo."},
                    {"term": "doctrine mode", "definition": "The reasoning constraint level: STRICT (full doctrine), HYBRID (doctrine + reflective), REFLECTIVE (emotional/process)."},
                ],
                "definitions": {
                    "core": "End-to-end process describes the full request lifecycle from user query through doctrine classification, reasoning, validation, and response delivery.",
                },
                "structural_logic": [
                    "Every interaction passes through two layers: dialog (fast) and cognition (async).",
                    "All LLM calls route through VexyKernel.reason() — no exceptions.",
                    "Post-LLM validation checks ORA, forbidden language, tier scope, and despair signals.",
                    "Response delivery via pub/sub on vexy_interaction:{wp_user_id}.",
                ],
                "constraints": [
                    "No capability may call call_ai() directly — must use kernel.",
                    "Dialog layer must respond in <250ms.",
                    "Post-LLM validation must run on every response.",
                ],
                "failure_modes": [
                    "Bypassing kernel for direct LLM calls.",
                    "Dialog layer blocking on cognition.",
                    "Skipping post-LLM validation.",
                ],
                "non_capabilities": [
                    "Cannot bypass VexyKernel.reason().",
                    "Cannot skip post-LLM validation.",
                    "Cannot deliver responses without pub/sub.",
                ],
            },
        }


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate doctrine playbooks from PathRuntime")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "playbooks"),
        help="Output directory for YAML playbooks",
    )
    parser.add_argument(
        "--path-dir",
        default=os.path.expanduser("~/path"),
        help="Path doctrine directory",
    )
    args = parser.parse_args()

    # Initialize PathRuntime
    from services.vexy_ai.intel.path_runtime import PathRuntime

    runtime = PathRuntime(path_dir=args.path_dir)
    try:
        runtime.load()
    except FileNotFoundError as e:
        print(f"Warning: {e} — generating with unloaded runtime")

    generator = PlaybookGenerator(runtime)
    print(f"Runtime hash: {generator.compute_runtime_hash()[:16]}...")
    print(f"Generating to: {args.output_dir}")
    generator.generate_all(args.output_dir)
