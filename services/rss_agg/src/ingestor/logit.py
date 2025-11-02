# util/logit.py
from __future__ import annotations
import os, sys, inspect, datetime

# ---------- config ----------
LEVELS = {"DEBUG":10, "INFO":20, "WARNING":30, "ERROR":40, "SUCCESS":25}
EMOJI  = {"DEBUG":"🪰", "INFO":"ℹ️", "WARNING":"⚠️", "ERROR":"❌", "SUCCESS":"✅"}

LOG_LEVEL   = (os.getenv("LOG_LEVEL") or "INFO").upper()
THRESHOLD   = LEVELS.get(LOG_LEVEL, 20)
MODULE_NAME = os.getenv("MODULE_NAME") or os.getenv("SERVICE_ID")  # optional override
TIMEZONE    = (os.getenv("LOG_TZ") or "UTC").upper()               # "UTC" or "LOCAL"

# ---------- helpers ----------
def _now_stamp() -> str:
    if TIMEZONE == "LOCAL":
        dt = datetime.datetime.now().astimezone()
        offs = dt.strftime("%z")
        offs = f"{offs[:3]}:{offs[3:]}" if len(offs) == 5 else ""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + offs
    dt = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def _caller_mod() -> str:
    if MODULE_NAME:
        return MODULE_NAME
    # try to get the import path of the caller
    frame = inspect.currentframe()
    for _ in range(3):  # climb a couple frames
        if frame: frame = frame.f_back
    mod = inspect.getmodule(frame)
    if mod and getattr(mod, "__name__", None):
        return mod.__name__
    return os.getenv("SERVICE_ID", "app")

def _emit(level: str, msg: str):
    if LEVELS.get(level, 999) < THRESHOLD:
        return
    # handle multi-line messages cleanly
    name = _caller_mod()
    stamp = _now_stamp()
    emo = EMOJI.get(level, "")
    for line in (msg.splitlines() or [""]):
        sys.stdout.write(f"{stamp} | {name} | {level} | {emo} | {line}\n")
    sys.stdout.flush()

# ---------- API ----------
def debug(msg: str):   _emit("DEBUG", msg)
def info(msg: str):    _emit("INFO", msg)
def warning(msg: str): _emit("WARNING", msg)
def error(msg: str):   _emit("ERROR", msg)
def success(msg: str): _emit("SUCCESS", msg)  # optional mid-level between INFO/WARNING

# alias you asked for
def logit(msg: str):   info(msg)