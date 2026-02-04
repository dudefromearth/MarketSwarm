from datetime import datetime, UTC
from typing import Dict, Any
import os

STATUS_EMOJI = {
    "INFO": "ℹ️",
    "WARN": "⚠️",
    "ERROR": "❌",
    "DEBUG": "🔍",
    "OK": "✅",
}

# Log level hierarchy (lower number = more severe)
LOG_LEVELS = {
    "ERROR": 0,
    "WARN": 1,
    "WARNING": 1,
    "INFO": 2,
    "OK": 2,
    "DEBUG": 3,
}


class LogUtil:
    """
    Two-phase logger:
      - Bootstrap phase: env-driven
      - Configured phase: config-driven

    Safe to use before and after SetupBase.
    Logging must NEVER raise.

    Log levels (from LOG_LEVEL env var):
      - ERROR: Only errors
      - WARNING: Warnings and errors
      - INFO: Normal operational info (default)
      - DEBUG: All messages including debug
    """

    def __init__(self, service_name: str):
        self.service_name = service_name

        # Phase 1: bootstrap (env only)
        # Support both LOG_LEVEL and legacy DEBUG_MASSIVE
        env_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_level = LOG_LEVELS.get(env_level, LOG_LEVELS["INFO"])

        # Legacy debug flag support
        if os.getenv("DEBUG_MASSIVE", "false").lower() == "true":
            self.log_level = LOG_LEVELS["DEBUG"]

        self.debug_enabled = self.log_level >= LOG_LEVELS["DEBUG"]
        self._configured = False

    # -------------------------------------------------
    # Configuration phase
    # -------------------------------------------------

    def configure_from_config(self, config: Dict[str, Any]) -> None:
        if self._configured:
            return

        try:
            # Check for LOG_LEVEL in config first
            cfg_level = str(config.get("LOG_LEVEL", "")).upper()
            if cfg_level and cfg_level in LOG_LEVELS:
                self.log_level = LOG_LEVELS[cfg_level]

            # Legacy DEBUG_MASSIVE support (overrides to DEBUG if true)
            cfg_debug = str(
                config.get("DEBUG_MASSIVE", "false")
            ).lower() == "true"
            if cfg_debug:
                self.log_level = LOG_LEVELS["DEBUG"]

            self.debug_enabled = self.log_level >= LOG_LEVELS["DEBUG"]
            self._configured = True

            level_name = [k for k, v in LOG_LEVELS.items() if v == self.log_level and k != "WARNING" and k != "OK"][0]
            self.info(
                f"[LOG CONFIGURED] level={level_name}",
                emoji="🧪" if self.debug_enabled else "🔊",
            )
        except Exception:
            # Logging must never break the process
            pass

    # -------------------------------------------------
    # Internal formatting
    # -------------------------------------------------

    def _stamp(self, level: str, message: str, emoji: str):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        symbol = emoji or STATUS_EMOJI.get(level, "")
        return f"[{now}][{self.service_name}][{level}]{symbol} {message}"

    def _emit(self, level: str, message: str, emoji: str = ""):
        try:
            # Check if this level should be emitted based on configured log level
            msg_level = LOG_LEVELS.get(level, LOG_LEVELS["INFO"])
            if msg_level > self.log_level:
                return
            print(self._stamp(level, message, emoji))
        except Exception:
            # Absolute last line of defense
            pass

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def info(self, message: str, emoji: str = STATUS_EMOJI["INFO"]):
        self._emit("INFO", message, emoji)

    def warn(self, message: str, emoji: str = STATUS_EMOJI["WARN"]):
        self._emit("WARN", message, emoji)

    def warning(self, message: str, emoji: str = STATUS_EMOJI["WARN"]):
        # Alias for compatibility with standard logging APIs
        self.warn(message, emoji)

    def error(self, message: str, emoji: str = STATUS_EMOJI["ERROR"]):
        self._emit("ERROR", message, emoji)

    def debug(self, message: str, emoji: str = STATUS_EMOJI["DEBUG"]):
        self._emit("DEBUG", message, emoji)

    def ok(self, message: str, emoji: str = STATUS_EMOJI["OK"]):
        self._emit("OK", message, emoji)