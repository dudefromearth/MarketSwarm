from __future__ import annotations
import os, sys, threading, datetime

# ---- constants ----
_LEVELS = {
    "DEBUG":10,
    "INFO":20,
    "SUCCESS":25,
    "WARNING":30,
    "ERROR":40
}
_EMOJI  = {
    "DEBUG":   "🪰",  # was "🐛"
    "INFO":    "ℹ️",
    "SUCCESS": "✅",
    "WARNING": "⚠️",
    "ERROR":   "❌",
}
def _stamp(tz: str) -> str:
    tz = (tz or "UTC").upper()
    if tz == "LOCAL":
        dt = datetime.datetime.now().astimezone()
        off = dt.strftime("%z")
        off = f"{off[:3]}:{off[3:]}" if len(off) == 5 else ""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + off
    dt = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

class Logit:
    """
    Prints EXACT format:
    TIMESTAMP | MODULENAME | STATUS | emoji | MESSAGE
    """
    def __init__(self,
                 module_name: str | None = None,
                 level: str | None = None,
                 tz: str | None = None):
        self.module_name = module_name or os.getenv("MODULE_NAME") or os.getenv("SERVICE_ID") or "app"
        self.level_name  = (level or os.getenv("LOG_LEVEL","INFO")).upper()
        self.level       = _LEVELS.get(self.level_name, 20)
        self.tz          = (tz or os.getenv("LOG_TZ","UTC")).upper()
        self._lock       = threading.Lock()

    def set_module(self, name: str): self.module_name = name or self.module_name
    def set_level(self, level: str):
        L = (level or "").upper()
        if L in _LEVELS: self.level_name, self.level = L, _LEVELS[L]
    def set_tz(self, tz: str): self.tz = (tz or "UTC").upper()

    def _emit(self, status: str, msg: str):
        if _LEVELS.get(status, 999) < self.level:
            return
        ts = _stamp(self.tz)
        emo = _EMOJI.get(status, "")
        lines = msg.splitlines() or [""]
        with self._lock:
            for line in lines:
                sys.stdout.write(f"{ts} | {self.module_name} | {status} | {emo} | {line}\n")
            sys.stdout.flush()

    # convenience methods
    def debug(self, msg: str):   self._emit("DEBUG",   msg)
    def info(self, msg: str):    self._emit("INFO",    msg)
    def success(self, msg: str): self._emit("SUCCESS", msg)
    def warning(self, msg: str): self._emit("WARNING", msg)
    def error(self, msg: str):   self._emit("ERROR",   msg)

# module-level singleton + short aliases
logit = Logit()
debug   = logit.debug
info    = logit.info
success = logit.success
warning = logit.warning
error   = logit.error