#!/usr/bin/env python3
"""
logutil.py — Canonical logging utility for MarketSwarm services

Provides structured logging with emoji support and config-driven behavior.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class LogUtil:
    """
    Structured logger for MarketSwarm services.

    Usage:
        logger = LogUtil("my_service")
        logger.info("starting up", emoji="🚀")
        logger.configure_from_config(config)
        logger.ok("ready to process")
    """

    # Default emoji map
    EMOJI = {
        "info": "ℹ️",
        "ok": "✅",
        "warn": "⚠️",
        "error": "❌",
        "debug": "🔍",
    }

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.debug_enabled = os.getenv("DEBUG", "false").lower() == "true"
        self.log_file: Optional[str] = None

    def configure_from_config(self, config: Dict[str, Any]) -> None:
        """
        Configure logger from service config.
        """
        # Check for debug mode in config
        if config.get("DEBUG", "false").lower() == "true":
            self.debug_enabled = True

        # Check for log file path
        log_path = config.get("LOG_FILE")
        if log_path:
            self.log_file = log_path

    def _format(self, level: str, message: str, emoji: str = "") -> str:
        """Format a log message."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if not emoji:
            emoji = self.EMOJI.get(level.lower(), "")
        return f"[{ts}] [{self.service_name}|{level.upper()}] {emoji} {message}"

    def _emit(self, level: str, message: str, emoji: str = "") -> None:
        """Emit a log message to stdout and optionally to file."""
        formatted = self._format(level, message, emoji)
        print(formatted)

        if self.log_file:
            try:
                with open(self.log_file, "a") as f:
                    f.write(formatted + "\n")
            except IOError:
                pass  # Silently fail on file write errors

    def info(self, message: str, emoji: str = "") -> None:
        """Log an info message."""
        self._emit("info", message, emoji or self.EMOJI["info"])

    def ok(self, message: str, emoji: str = "") -> None:
        """Log a success message."""
        self._emit("ok", message, emoji or self.EMOJI["ok"])

    def warn(self, message: str, emoji: str = "") -> None:
        """Log a warning message."""
        self._emit("warn", message, emoji or self.EMOJI["warn"])

    def error(self, message: str, emoji: str = "") -> None:
        """Log an error message."""
        self._emit("error", message, emoji or self.EMOJI["error"])

    def debug(self, message: str, emoji: str = "") -> None:
        """Log a debug message (only if debug mode enabled)."""
        if self.debug_enabled:
            self._emit("debug", message, emoji or self.EMOJI["debug"])


# Legacy functions for backwards compatibility
STATUS_EMOJI = {
    "INFO": "ℹ️",
    "WARN": "⚠️",
    "ERROR": "❌",
    "DEBUG": "🔍",
}


def format_log(status: str, description: str, context: str = "") -> str:
    """Legacy format function."""
    ts = datetime.now(timezone.utc).isoformat() + "Z"
    emoji = STATUS_EMOJI.get(status, "❓")
    return f"[{ts}] {status} {emoji} {description}: {context}"
