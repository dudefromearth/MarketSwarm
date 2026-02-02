# services/copilot/intel/prompt_orchestrator.py
"""
PromptOrchestrationManager - Handles multi-prompt relationships.

Orchestration modes:
- parallel: All alerts evaluate independently, no side effects
- overlapping: Multiple alerts can be active simultaneously
- sequential: A accomplishes -> A dormant -> B activates (relay with fresh reference)
"""

import json
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .reference_state_capture import ReferenceStateCaptureService


@dataclass
class OrchestrationResult:
    """Result of orchestration handling."""
    alert_id: str
    action: str  # "none", "activate", "deactivate", "accomplish"
    fresh_reference_needed: bool
    reason: str


class PromptOrchestrationManager:
    """
    Manages relationships between multiple prompt alerts.

    Handles:
    - Parallel execution (independent alerts)
    - Overlapping execution (both active until objective met)
    - Sequential execution (relay with gates)
    """

    def __init__(
        self,
        db=None,
        reference_service: Optional[ReferenceStateCaptureService] = None,
        logger=None,
    ):
        self._db = db
        self._reference_service = reference_service or ReferenceStateCaptureService(logger)
        self._logger = logger

    def _log(self, msg: str, level: str = "info"):
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            fn(msg)

    async def handle_stage_transition(
        self,
        alert_id: str,
        new_stage: str,
        all_alerts: List[Dict[str, Any]],
        strategy_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> List[OrchestrationResult]:
        """
        Handle side effects of a stage transition.

        When an alert transitions stages, this determines what happens
        to related alerts in the same orchestration group.

        Args:
            alert_id: The alert that transitioned
            new_stage: The stage it transitioned to
            all_alerts: All alerts in the system (or group)
            strategy_data: Current strategy state (for fresh reference capture)
            market_data: Current market data

        Returns:
            List of OrchestrationResults describing actions to take
        """
        results = []

        # Find the transitioning alert
        alert = next((a for a in all_alerts if a.get("id") == alert_id), None)
        if not alert:
            return results

        orchestration_mode = alert.get("orchestration_mode", "parallel")
        group_id = alert.get("orchestration_group_id")

        # Parallel mode: no side effects
        if orchestration_mode == "parallel":
            results.append(OrchestrationResult(
                alert_id=alert_id,
                action="none",
                fresh_reference_needed=False,
                reason="Parallel mode - no side effects"
            ))
            return results

        # Get alerts in the same group
        if group_id:
            group_alerts = [
                a for a in all_alerts
                if a.get("orchestration_group_id") == group_id
            ]
        else:
            # No group - only handle this alert
            group_alerts = [alert]

        # Overlapping mode: both stay active until objective met
        if orchestration_mode == "overlapping":
            return self._handle_overlapping_transition(
                alert, new_stage, group_alerts
            )

        # Sequential mode: relay with gates
        if orchestration_mode == "sequential":
            return await self._handle_sequential_transition(
                alert, new_stage, group_alerts, strategy_data, market_data
            )

        return results

    def _handle_overlapping_transition(
        self,
        alert: Dict[str, Any],
        new_stage: str,
        group_alerts: List[Dict[str, Any]],
    ) -> List[OrchestrationResult]:
        """
        Handle overlapping orchestration transition.

        In overlapping mode, multiple alerts can be active at the same time.
        When one reaches 'accomplished', it becomes dormant but others continue.
        """
        results = []

        if new_stage == "accomplished":
            # This alert becomes dormant, others continue
            results.append(OrchestrationResult(
                alert_id=alert["id"],
                action="accomplish",
                fresh_reference_needed=False,
                reason="Overlapping mode - accomplished, going dormant"
            ))

            # Log the remaining active alerts
            remaining = [
                a for a in group_alerts
                if a["id"] != alert["id"] and a.get("lifecycle_state") == "active"
            ]
            if remaining:
                self._log(f"Overlapping group: {len(remaining)} alerts still active after {alert['id']} accomplished")

        else:
            # Regular transition - no side effects
            results.append(OrchestrationResult(
                alert_id=alert["id"],
                action="none",
                fresh_reference_needed=False,
                reason=f"Overlapping mode - stage transition to {new_stage}"
            ))

        return results

    async def _handle_sequential_transition(
        self,
        alert: Dict[str, Any],
        new_stage: str,
        group_alerts: List[Dict[str, Any]],
        strategy_data: Optional[Dict[str, Any]],
        market_data: Optional[Dict[str, Any]],
    ) -> List[OrchestrationResult]:
        """
        Handle sequential orchestration transition.

        In sequential mode:
        - Alerts have a sequence order
        - When A accomplishes, A goes dormant, B activates
        - B gets a fresh reference state captured at activation
        """
        results = []

        if new_stage != "accomplished":
            # Regular transition - no side effects
            results.append(OrchestrationResult(
                alert_id=alert["id"],
                action="none",
                fresh_reference_needed=False,
                reason=f"Sequential mode - stage transition to {new_stage}"
            ))
            return results

        # Alert accomplished - handle relay
        results.append(OrchestrationResult(
            alert_id=alert["id"],
            action="accomplish",
            fresh_reference_needed=False,
            reason="Sequential mode - accomplished, going dormant"
        ))

        # Find next alert in sequence
        current_order = alert.get("sequence_order", 0)
        next_alert = self._find_next_in_sequence(alert, group_alerts)

        if next_alert:
            # Check if next alert was waiting for this one
            activates_after = next_alert.get("activates_after_alert_id")
            is_waiting = next_alert.get("lifecycle_state") == "dormant"

            if activates_after == alert["id"] or is_waiting:
                # Activate next alert with fresh reference
                results.append(OrchestrationResult(
                    alert_id=next_alert["id"],
                    action="activate",
                    fresh_reference_needed=True,
                    reason=f"Sequential relay - activated after {alert['id']} accomplished"
                ))

                self._log(
                    f"Sequential relay: {alert['id']} -> {next_alert['id']}, "
                    f"fresh reference needed"
                )

        return results

    def _find_next_in_sequence(
        self,
        current_alert: Dict[str, Any],
        group_alerts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Find the next alert in a sequential group."""
        current_order = current_alert.get("sequence_order", 0)

        # Sort by sequence order
        sorted_alerts = sorted(
            group_alerts,
            key=lambda a: a.get("sequence_order", 0)
        )

        # Find next after current
        for alert in sorted_alerts:
            if alert.get("sequence_order", 0) > current_order:
                return alert

            # Also check if this alert explicitly follows the current one
            if alert.get("activates_after_alert_id") == current_alert["id"]:
                return alert

        return None

    def create_orchestration_group(
        self,
        alerts: List[Dict[str, Any]],
        mode: str = "parallel",
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Create an orchestration group from a list of alerts.

        Args:
            alerts: List of alert dicts to group
            mode: Orchestration mode (parallel, overlapping, sequential)

        Returns:
            Tuple of (group_id, updated alerts with group assignments)
        """
        import uuid
        group_id = str(uuid.uuid4())

        updated_alerts = []
        for i, alert in enumerate(alerts):
            updated = {
                **alert,
                "orchestration_mode": mode,
                "orchestration_group_id": group_id,
                "sequence_order": i,  # Preserve order for sequential
            }

            # For sequential, set activation dependencies
            if mode == "sequential" and i > 0:
                updated["activates_after_alert_id"] = alerts[i - 1].get("id")
                # First alert is active, rest are dormant until activated
                if i > 0:
                    updated["lifecycle_state"] = "dormant"

            updated_alerts.append(updated)

        return group_id, updated_alerts

    def validate_group(self, alerts: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Validate an orchestration group configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not alerts:
            return False, "Group cannot be empty"

        # Check all have same mode and group_id
        modes = set(a.get("orchestration_mode") for a in alerts)
        groups = set(a.get("orchestration_group_id") for a in alerts)

        if len(modes) > 1:
            return False, "All alerts in group must have same orchestration mode"

        if len(groups) > 1:
            return False, "All alerts in group must have same group ID"

        mode = list(modes)[0]

        # Sequential-specific validation
        if mode == "sequential":
            orders = [a.get("sequence_order", 0) for a in alerts]
            if len(orders) != len(set(orders)):
                return False, "Sequential alerts must have unique sequence orders"

            # Check activation chain is valid
            for alert in alerts:
                activates_after = alert.get("activates_after_alert_id")
                if activates_after:
                    found = any(a.get("id") == activates_after for a in alerts)
                    if not found:
                        return False, f"Alert references non-existent activation dependency: {activates_after}"

        return True, ""

    async def activate_alert(
        self,
        alert_id: str,
        strategy_data: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Activate a dormant alert with fresh reference capture.

        Args:
            alert_id: Alert to activate
            strategy_data: Current strategy state
            market_data: Current market data

        Returns:
            Updated alert dict with activation timestamp and reference info
        """
        now = datetime.now(UTC).isoformat()

        # Capture fresh reference state
        reference = await self._reference_service.capture_for_sequential_activation(
            alert_id,
            strategy_data.get("id", ""),
            strategy_data,
            market_data,
        )

        return {
            "lifecycle_state": "active",
            "current_stage": "watching",
            "activated_at": now,
            "updated_at": now,
            "_fresh_reference": reference.to_snapshot_dict(),
        }

    async def deactivate_alert(
        self,
        alert_id: str,
        reason: str = "accomplished",
    ) -> Dict[str, Any]:
        """
        Deactivate an active alert (set to dormant or accomplished).

        Args:
            alert_id: Alert to deactivate
            reason: Why it's being deactivated

        Returns:
            Updated alert dict
        """
        now = datetime.now(UTC).isoformat()

        state = "accomplished" if reason == "accomplished" else "dormant"

        return {
            "lifecycle_state": state,
            "accomplished_at": now if state == "accomplished" else None,
            "updated_at": now,
        }

    def get_group_status(
        self,
        group_alerts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Get status summary for an orchestration group.

        Args:
            group_alerts: All alerts in the group

        Returns:
            Status summary dict
        """
        if not group_alerts:
            return {"error": "No alerts in group"}

        mode = group_alerts[0].get("orchestration_mode", "parallel")
        group_id = group_alerts[0].get("orchestration_group_id")

        active = [a for a in group_alerts if a.get("lifecycle_state") == "active"]
        dormant = [a for a in group_alerts if a.get("lifecycle_state") == "dormant"]
        accomplished = [a for a in group_alerts if a.get("lifecycle_state") == "accomplished"]

        return {
            "group_id": group_id,
            "mode": mode,
            "total": len(group_alerts),
            "active": len(active),
            "dormant": len(dormant),
            "accomplished": len(accomplished),
            "active_alerts": [a.get("id") for a in active],
            "next_in_sequence": self._find_next_in_sequence(
                active[0], group_alerts
            ).get("id") if active and mode == "sequential" else None,
        }
