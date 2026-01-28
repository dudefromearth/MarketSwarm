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


class LogUtil:
    """
    Two-phase logger:
      - Bootstrap phase: env-driven
      - Configured phase: config-driven

    Safe to use before and after SetupBase.
    Logging must NEVER raise.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name

        # Phase 1: bootstrap (env only)
        self.debug_enabled = (
            os.getenv("DEBUG_MASSIVE", "false").lower() == "true"
        )

        self._configured = False

    # -------------------------------------------------
    # Configuration phase
    # -------------------------------------------------

    def configure_from_config(self, config: Dict[str, Any]) -> None:
        if self._configured:
            return

        try:
            cfg_debug = str(
                config.get("DEBUG_MASSIVE", "false")
            ).lower() == "true"

            self.debug_enabled = cfg_debug
            self._configured = True

            self.info(
                f"[LOG CONFIGURED] debug={'ON' if cfg_debug else 'OFF'}",
                emoji="🧪" if cfg_debug else "🔊",
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
            if level == "DEBUG" and not self.debug_enabled:
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