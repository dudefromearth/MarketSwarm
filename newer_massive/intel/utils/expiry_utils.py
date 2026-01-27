# services/massive/shared/expiry_utils.py

from datetime import date

def current_trading_expiry_yyyymmdd() -> str:
    """Return current trading day expiry as YYYYMMDD."""
    return date.today().strftime("%Y%m%d")

def current_trading_expiry_iso() -> str:
    """Return current trading day expiry as YYYY-MM-DD."""
    return date.today().isoformat()