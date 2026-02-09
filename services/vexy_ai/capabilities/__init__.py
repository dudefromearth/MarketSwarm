"""
Vexy Capabilities - Domain-specific functionality.

Each capability is a self-contained domain that provides:
- HTTP routes (optional)
- Background tasks (optional)
- Event subscriptions (optional)
- Event publishing

Capabilities are loaded based on configuration and
orchestrated by the Vexy core.

Available capabilities:
- chat: User-facing conversation
- journal: Journal integration
- playbook: Playbook authoring
- routine: Routine panel
- ml: ML thresholds
- commentary: Epoch/event engine
- health_monitor: Service health monitoring
- healer: Self-healing protocols
- mesh: Multi-node communication
"""
