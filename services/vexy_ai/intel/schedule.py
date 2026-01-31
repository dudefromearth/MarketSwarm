#!/usr/bin/env python3
"""
schedule.py — Trading day detection and epoch schedule management for Vexy AI

Determines whether current day is a trading day or non-trading day,
and provides the appropriate epoch schedule from config.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List, Optional
import pytz


# US market timezone
ET = pytz.timezone("America/New_York")


def get_current_et() -> datetime:
    """Get current datetime in Eastern Time."""
    return datetime.now(ET)


def is_weekend(dt: Optional[datetime] = None) -> bool:
    """Check if date is Saturday or Sunday."""
    dt = dt or get_current_et()
    return dt.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def is_market_holiday(dt: Optional[datetime] = None, holidays: List[str] = None) -> bool:
    """
    Check if date is a market holiday.

    Args:
        dt: Datetime to check (defaults to now ET)
        holidays: List of holiday dates as "YYYY-MM-DD" strings
    """
    if not holidays:
        return False
    dt = dt or get_current_et()
    date_str = dt.strftime("%Y-%m-%d")
    return date_str in holidays


def is_trading_day(config: Dict[str, Any], dt: Optional[datetime] = None) -> bool:
    """
    Determine if current day is a trading day.

    Returns False for weekends and market holidays.
    """
    dt = dt or get_current_et()

    if is_weekend(dt):
        return False

    holidays = config.get("market_holidays", [])
    if is_market_holiday(dt, holidays):
        return False

    return True


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """
    Check if current time is within US market hours (9:30 AM - 4:00 PM ET).
    Extended hours: 8:00 AM - 4:15 PM for pre/post market epochs.
    """
    dt = dt or get_current_et()
    hour = dt.hour
    minute = dt.minute

    # Extended hours: 8:00 AM to 4:15 PM ET
    if hour < 8:
        return False
    if hour > 16 or (hour == 16 and minute > 15):
        return False

    return True


def get_day_of_week(dt: Optional[datetime] = None) -> str:
    """Get day name (lowercase) for epoch filtering."""
    dt = dt or get_current_et()
    return dt.strftime("%A").lower()


def get_active_schedule(config: Dict[str, Any], dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Get the active schedule configuration for the current day.

    Returns trading_days config on trading days, non_trading_days otherwise.
    """
    if is_trading_day(config, dt):
        return config.get("trading_days", {})
    else:
        return config.get("non_trading_days", {})


def get_epochs_for_day(config: Dict[str, Any], dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Get the list of epochs for the current day.

    On trading days: returns trading_days.epochs
    On non-trading days: returns non_trading_days.scheduled_epochs,
                         filtered by day if epoch has a "day" field
    """
    dt = dt or get_current_et()
    schedule = get_active_schedule(config, dt)

    if is_trading_day(config, dt):
        return schedule.get("epochs", [])
    else:
        # Non-trading day epochs
        epochs = schedule.get("scheduled_epochs", [])
        day_name = get_day_of_week(dt)

        # Filter epochs that are specific to a day (e.g., Sunday Prep)
        filtered = []
        for epoch in epochs:
            epoch_day = epoch.get("day")
            if epoch_day is None or epoch_day == day_name:
                filtered.append(epoch)

        return filtered


def get_system_preferences(config: Dict[str, Any], dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Get system preferences, with non-trading day overrides applied if applicable.
    """
    base_prefs = config.get("system_preferences", {})

    if not is_trading_day(config, dt):
        schedule = config.get("non_trading_days", {})
        overrides = schedule.get("system_preferences_override", {})
        # Merge overrides into base
        return {**base_prefs, **overrides}

    return base_prefs


def get_reflection_dial_config(config: Dict[str, Any], dial_value: float) -> Dict[str, Any]:
    """
    Get the reflection dial configuration for a given dial value.

    Returns the threshold config (tone, voice, partitions, max_length)
    that matches the dial value.
    """
    thresholds = config.get("reflection_dial_behavior", {}).get("thresholds", {})

    for name, threshold in thresholds.items():
        range_min, range_max = threshold.get("range", [0, 1])
        if range_min <= dial_value <= range_max:
            return {
                "threshold_name": name,
                **threshold,
            }

    # Default to gentle if no match
    return thresholds.get("gentle", {
        "threshold_name": "gentle",
        "range": [0.0, 0.3],
        "tone": "grounded",
        "voice": "Sage",
        "partitions": ["tldr", "structure"],
        "max_length": 200,
    })


def get_article_trigger_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the article trigger configuration for non-trading days.
    """
    schedule = config.get("non_trading_days", {})
    return schedule.get("article_trigger", {
        "min_articles": 2,
        "batch_window_minutes": 60,
        "max_messages_per_day": 8,
        "cooldown_minutes": 45,
    })


def get_article_commentary_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the article commentary configuration for non-trading days.
    """
    schedule = config.get("non_trading_days", {})
    return schedule.get("article_commentary", {
        "enabled": True,
        "voice": "Observer",
        "partitions": ["tldr", "tension"],
        "reflection_dial": 0.4,
    })


def get_response_format(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the response format configuration (partitions and voice rules).
    """
    return config.get("response_format", {})


def get_partition_config(config: Dict[str, Any], partition_name: str) -> Dict[str, Any]:
    """
    Get the configuration for a specific response partition.
    """
    response_format = get_response_format(config)
    partitions = response_format.get("partitions", {})
    return partitions.get(partition_name, {})
