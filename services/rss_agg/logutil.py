from __future__ import annotations

from datetime import datetime


def _timestamp() -> str:
    # ISO8601 without microseconds for legibility
    return datetime.now().isoformat(timespec="seconds")


def log(service: str, status: str, emoji: str, message: str) -> None:
    """
    Standard logging format for all services.

    [timestamp][component][status] emoji message

    status examples: INFO, WARN, ERROR, DEBUG
    emoji examples: ✅, ⚠️, ❌, ℹ️
    """
    print(f"[{_timestamp()}][{service}][{status}] {emoji} {message}")