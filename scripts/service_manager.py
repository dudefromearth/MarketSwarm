#!/usr/bin/env python3
"""
MarketSwarm Node Admin

A self-configuring admin server for MarketSwarm nodes.
Manages services, provides web UI, and discovers node configuration
from truth.json.

Can be pointed at any MarketSwarm repo to manage that node.

Configuration priority:
  1. CLI argument: --repo /path/to/repo
  2. Environment variable: MARKETSWARM_REPO
  3. Config file: ~/.marketswarm/config.json
  4. Auto-detect: derive from script location
"""

# ============================================================
# Admin Server Version & Info
# ============================================================
ADMIN_VERSION = "1.2.0"
ADMIN_BUILD_DATE = "2026-02-10"
ADMIN_FEATURES = [
    {"id": "service-mgmt", "name": "Service Management", "desc": "Start, stop, restart services"},
    {"id": "log-viewer", "name": "Log Viewer", "desc": "View and tail service logs"},
    {"id": "env-overrides", "name": "ENV Overrides", "desc": "Override truth.json env vars per service"},
    {"id": "analytics", "name": "Analytics Dashboard", "desc": "View service instrumentation data"},
    {"id": "alerts", "name": "System Alerts", "desc": "Auto-detect and display errors from services and analytics"},
    {"id": "self-config", "name": "Self-Configuring", "desc": "Auto-discover node from repo path"},
    {"id": "live-status", "name": "Live Status", "desc": "Auto-refresh service status every 5s"},
    {"id": "uptime-tracking", "name": "Uptime Tracking", "desc": "Track service uptime when started via admin"},
    {"id": "health-monitor", "name": "Health Monitor", "desc": "Deep Redis, heartbeat, and HTTP health monitoring with scoring and notifications"},
]

import os
import sys
import json
import time
import signal
import subprocess
import argparse
import threading
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime
from urllib import request as urllib_request

# ============================================================
# Configuration Discovery
# ============================================================
CONFIG_FILE = Path.home() / ".marketswarm" / "config.json"
SCRIPT_DIR = Path(__file__).parent.resolve()


def load_admin_config() -> dict:
    """Load admin config from ~/.marketswarm/config.json if it exists."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_admin_config(config: dict):
    """Save admin config to ~/.marketswarm/config.json."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def discover_repo_path(cli_repo: Optional[str] = None) -> Path:
    """
    Discover the MarketSwarm repo path.

    Priority:
      1. CLI argument (if provided)
      2. MARKETSWARM_REPO environment variable
      3. Config file (~/.marketswarm/config.json)
      4. Auto-detect from script location
    """
    # 1. CLI argument
    if cli_repo:
        path = Path(cli_repo).resolve()
        if _validate_repo(path):
            return path
        print(f"Warning: {path} doesn't look like a MarketSwarm repo")

    # 2. Environment variable
    env_repo = os.environ.get("MARKETSWARM_REPO")
    if env_repo:
        path = Path(env_repo).resolve()
        if _validate_repo(path):
            return path
        print(f"Warning: MARKETSWARM_REPO={env_repo} doesn't look like a MarketSwarm repo")

    # 3. Config file
    config = load_admin_config()
    if "repo" in config:
        path = Path(config["repo"]).resolve()
        if _validate_repo(path):
            return path
        print(f"Warning: Configured repo {path} doesn't look like a MarketSwarm repo")

    # 4. Auto-detect from script location
    # Assume script is in <repo>/scripts/
    auto_path = SCRIPT_DIR.parent
    if _validate_repo(auto_path):
        return auto_path

    # Fallback to auto-detected path even if validation fails
    return auto_path


def _validate_repo(path: Path) -> bool:
    """Check if path looks like a MarketSwarm repo."""
    # Must have services/ directory and either truth.json or truth/ components
    if not path.is_dir():
        return False

    has_services = (path / "services").is_dir()
    has_truth = (path / "scripts" / "truth.json").exists() or (path / "truth").is_dir()

    return has_services and has_truth


# Default paths (will be reconfigured after repo discovery)
ROOT = SCRIPT_DIR.parent  # Temporary, reconfigured in configure_paths()
VENV_PY = ROOT / ".venv" / "bin" / "python"
LOGS_DIR = ROOT / "logs"
PID_DIR = ROOT / ".pids"
TRUTH_PATH = ROOT / "scripts" / "truth.json"
ADMIN_UI_DIR = SCRIPT_DIR / "admin_ui"


def configure_paths(repo_path: Path):
    """Configure all paths based on the repo location."""
    global ROOT, VENV_PY, LOGS_DIR, PID_DIR, TRUTH_PATH, ADMIN_UI_DIR

    ROOT = repo_path
    VENV_PY = ROOT / ".venv" / "bin" / "python"
    LOGS_DIR = ROOT / "logs"
    PID_DIR = ROOT / ".pids"
    TRUTH_PATH = ROOT / "scripts" / "truth.json"
    # Admin UI stays with the script, not the repo
    ADMIN_UI_DIR = SCRIPT_DIR / "admin_ui"

    # Ensure directories exist
    LOGS_DIR.mkdir(exist_ok=True)
    PID_DIR.mkdir(exist_ok=True)


@dataclass
class ServiceConfig:
    """Configuration for a service."""
    name: str
    description: str
    main_module: str  # Path relative to ROOT
    port: int = 0  # 0 means no HTTP port
    env: Dict[str, str] = field(default_factory=dict)
    python: bool = True  # True for Python services, False for Node.js
    dependencies: List[str] = field(default_factory=list)


def load_services_from_truth() -> Dict[str, ServiceConfig]:
    """Load service definitions from truth.json."""
    if not TRUTH_PATH.exists():
        print(f"Warning: {TRUTH_PATH} not found, using defaults")
        return _get_fallback_services()

    try:
        truth = json.loads(TRUTH_PATH.read_text())
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to parse {TRUTH_PATH}: {e}")
        return _get_fallback_services()

    services = {}
    components = truth.get("components", {})

    for name, comp in components.items():
        meta = comp.get("meta", {})
        env = comp.get("env", {})
        dependencies = comp.get("dependencies", [])

        # Detect service type (Node.js vs Python)
        is_python = name not in {"sse", "vexy_proxy"}

        # Detect port from env vars
        port = 0
        port_key = f"{name.upper()}_PORT"
        if port_key in env:
            try:
                port = int(env[port_key])
            except (ValueError, TypeError):
                pass
        elif "SSE_PORT" in env:
            try:
                port = int(env["SSE_PORT"])
            except (ValueError, TypeError):
                pass
        elif "JOURNAL_PORT" in env:
            try:
                port = int(env["JOURNAL_PORT"])
            except (ValueError, TypeError):
                pass
        elif "COPILOT_PORT" in env:
            try:
                port = int(env["COPILOT_PORT"])
            except (ValueError, TypeError):
                pass

        # Build main module path
        if is_python:
            main_module = f"services/{name}/main.py"
        else:
            main_module = f"services/{name}/src/index.js"

        services[name] = ServiceConfig(
            name=name,
            description=meta.get("description", meta.get("name", name)),
            main_module=main_module,
            port=port,
            env=env,
            python=is_python,
            dependencies=dependencies,
        )

    return services


def _get_fallback_services() -> Dict[str, ServiceConfig]:
    """Fallback service definitions if truth.json is unavailable."""
    return {
        "massive": ServiceConfig(
            name="massive",
            description="Market Model Engine",
            main_module="services/massive/main.py",
            env={"MASSIVE_WS_ENABLED": "true"},
        ),
        "rss_agg": ServiceConfig(
            name="rss_agg",
            description="RSS Aggregator",
            main_module="services/rss_agg/main.py",
            env={"PIPELINE_MODE": "full"},
        ),
        "vexy_ai": ServiceConfig(
            name="vexy_ai",
            description="AI Play-by-Play",
            main_module="services/vexy_ai/main.py",
            env={"VEXY_MODE": "full"},
        ),
        "sse": ServiceConfig(
            name="sse",
            description="SSE Gateway",
            main_module="services/sse/src/index.js",
            port=3001,
            python=False,
            env={
                "TRUTH_REDIS_URL": "redis://127.0.0.1:6379",
                "TRUTH_REDIS_KEY": "truth",
                "SSE_PORT": "3001",
            },
        ),
        "journal": ServiceConfig(
            name="journal",
            description="Journal Service",
            main_module="services/journal/main.py",
            port=3002,
            env={"JOURNAL_PORT": "3002"},
        ),
        "content_anal": ServiceConfig(
            name="content_anal",
            description="Content Analysis",
            main_module="services/content_anal/main.py",
        ),
        "copilot": ServiceConfig(
            name="copilot",
            description="Copilot (MEL/ADI/Alerts)",
            main_module="services/copilot/main.py",
            port=8095,
            env={
                "COPILOT_PORT": "8095",
                "COPILOT_MEL_ENABLED": "true",
                "COPILOT_ADI_ENABLED": "true",
                "COPILOT_ALERTS_ENABLED": "true",
            },
        ),
    }


# Load services from truth.json
SERVICES: Dict[str, ServiceConfig] = load_services_from_truth()

# Common environment for all services
COMMON_ENV = {
    "SYSTEM_REDIS_URL": "redis://127.0.0.1:6379",
    "MARKET_REDIS_URL": "redis://127.0.0.1:6380",
    "INTEL_REDIS_URL": "redis://127.0.0.1:6381",
    "PYTHONUNBUFFERED": "1",  # Force immediate log output to files
}


class ServiceManager:
    """Manages MarketSwarm services."""

    def __init__(self):
        self.root = ROOT
        self.venv_py = VENV_PY
        self.logs_dir = LOGS_DIR
        self.pid_dir = PID_DIR

    def _pid_file(self, name: str) -> Path:
        return self.pid_dir / f"{name}.pid"

    def _start_file(self, name: str) -> Path:
        return self.pid_dir / f"{name}.started"

    def _log_file(self, name: str) -> Path:
        return self.logs_dir / f"{name}.log"

    def _read_start_time(self, name: str) -> Optional[str]:
        """Read start timestamp from file."""
        start_file = self._start_file(name)
        if start_file.exists():
            try:
                return start_file.read_text().strip()
            except IOError:
                return None
        return None

    def _write_start_time(self, name: str):
        """Write current timestamp to start file."""
        self._start_file(name).write_text(datetime.now().isoformat())

    def _remove_start_time(self, name: str):
        """Remove start time file."""
        start_file = self._start_file(name)
        if start_file.exists():
            start_file.unlink()

    def _read_pid(self, name: str) -> Optional[int]:
        """Read PID from file."""
        pid_file = self._pid_file(name)
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                return pid
            except (ValueError, IOError):
                return None
        return None

    def _write_pid(self, name: str, pid: int):
        """Write PID to file."""
        self._pid_file(name).write_text(str(pid))

    def _remove_pid(self, name: str):
        """Remove PID file."""
        pid_file = self._pid_file(name)
        if pid_file.exists():
            pid_file.unlink()

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def _get_port_pid(self, port: int) -> Optional[int]:
        """Get PID of process using a port."""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
        except Exception:
            pass
        return None

    def get_status(self, name: str) -> dict:
        """Get status of a service."""
        if name not in SERVICES:
            return {"error": f"Unknown service: {name}"}

        config = SERVICES[name]
        pid = self._read_pid(name)
        running = False
        actual_pid = None

        # Check if PID from file is running
        if pid and self._is_process_running(pid):
            running = True
            actual_pid = pid
        else:
            # Check by port if applicable
            if config.port > 0 and self._is_port_in_use(config.port):
                actual_pid = self._get_port_pid(config.port)
                running = actual_pid is not None

        # Clean up stale PID file
        if not running and pid:
            self._remove_pid(name)
            self._remove_start_time(name)

        # Calculate uptime if running
        started_at = None
        uptime_seconds = None
        if running:
            started_at = self._read_start_time(name)
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at)
                    uptime_seconds = int((datetime.now() - start_dt).total_seconds())
                except (ValueError, TypeError):
                    pass

        return {
            "name": name,
            "description": config.description,
            "port": config.port if config.port > 0 else None,
            "running": running,
            "pid": actual_pid,
            "started_at": started_at,
            "uptime_seconds": uptime_seconds,
        }

    def get_all_status(self) -> List[dict]:
        """Get status of all services."""
        return [self.get_status(name) for name in SERVICES]

    def start(self, name: str, foreground: bool = False, extra_env: dict = None) -> dict:
        """Start a service."""
        if name not in SERVICES:
            return {"success": False, "error": f"Unknown service: {name}"}

        config = SERVICES[name]
        status = self.get_status(name)

        if status["running"]:
            return {"success": True, "message": f"{name} is already running", "pid": status["pid"]}

        # Build environment
        env = os.environ.copy()
        env.update(COMMON_ENV)
        # Skip ${VAR} template references — let setup_base resolve them
        # from Redis truth instead of injecting unresolved literals
        for k, v in config.env.items():
            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                continue
            env[k] = v
        env["SERVICE_ID"] = name
        if extra_env:
            env.update(extra_env)

        # Build command
        main_path = self.root / config.main_module
        if not main_path.exists():
            return {"success": False, "error": f"Main module not found: {main_path}"}

        # Python services run from ROOT (they add ROOT to sys.path)
        # Node.js services run from their service directory
        if config.python:
            if not self.venv_py.exists():
                return {"success": False, "error": f"Python venv not found: {self.venv_py}"}
            cmd = [str(self.venv_py), str(main_path)]
            cwd = str(self.root)
        else:
            # Node.js service runs from its directory with increased memory limit
            cmd = ["node", "--max-old-space-size=8192", main_path.name]
            cwd = str(main_path.parent)

        if foreground:
            # Run in foreground (exec)
            os.chdir(cwd)
            os.environ.update(env)
            os.execv(cmd[0], cmd)
            # Never returns
        else:
            # Run in background
            log_file = self._log_file(name)

            with open(log_file, 'a') as log:
                log.write(f"\n{'='*60}\n")
                log.write(f"Starting {name} at {datetime.now().isoformat()}\n")
                log.write(f"Command: {' '.join(cmd)}\n")
                log.write(f"{'='*60}\n\n")
                log.flush()

                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # Detach from terminal
                )

            # Wait a moment and check if it started
            time.sleep(2)

            if process.poll() is not None:
                # Process exited
                return {
                    "success": False,
                    "error": f"{name} exited immediately. Check {log_file}",
                    "exit_code": process.returncode,
                }

            # Save PID and start time
            self._write_pid(name, process.pid)
            self._write_start_time(name)

            return {
                "success": True,
                "message": f"{name} started",
                "pid": process.pid,
                "log": str(log_file),
            }

    def stop(self, name: str, force: bool = False) -> dict:
        """Stop a service."""
        if name not in SERVICES:
            return {"success": False, "error": f"Unknown service: {name}"}

        status = self.get_status(name)

        if not status["running"]:
            return {"success": True, "message": f"{name} is not running"}

        pid = status["pid"]
        if not pid:
            return {"success": False, "error": "Could not determine PID"}

        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            for _ in range(10):  # Wait up to 5 seconds
                time.sleep(0.5)
                if not self._is_process_running(pid):
                    self._remove_pid(name)
                    self._remove_start_time(name)
                    return {"success": True, "message": f"{name} stopped"}

            # Force kill if still running
            if force or True:  # Always force after timeout
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)

            if not self._is_process_running(pid):
                self._remove_pid(name)
                self._remove_start_time(name)
                return {"success": True, "message": f"{name} stopped (forced)"}
            else:
                return {"success": False, "error": f"Failed to stop {name}"}

        except ProcessLookupError:
            self._remove_pid(name)
            self._remove_start_time(name)
            return {"success": True, "message": f"{name} already stopped"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restart(self, name: str) -> dict:
        """Restart a service."""
        stop_result = self.stop(name)
        if not stop_result.get("success", False) and "not running" not in stop_result.get("message", ""):
            return stop_result

        time.sleep(1)
        return self.start(name)

    def start_all(self, extra_env: dict = None, service_env: dict = None) -> List[dict]:
        """Start all services with optional global and per-service env overrides."""
        results = []
        for name in SERVICES:
            # Merge global env with service-specific env
            env = dict(extra_env or {})
            if service_env and name in service_env:
                env.update({k: str(v) for k, v in service_env[name].items()})
            result = self.start(name, extra_env=env)
            result["name"] = name
            results.append(result)
        return results

    def stop_all(self) -> List[dict]:
        """Stop all services."""
        results = []
        for name in SERVICES:
            result = self.stop(name)
            result["name"] = name
            results.append(result)
        return results

    def logs(self, name: str, lines: int = 50) -> dict:
        """Get recent logs for a service."""
        if name not in SERVICES:
            return {"error": f"Unknown service: {name}"}

        log_file = self._log_file(name)
        if not log_file.exists():
            return {"name": name, "logs": "(no logs)"}

        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return {"name": name, "logs": "".join(recent)}
        except Exception as e:
            return {"error": str(e)}


def check_redis() -> dict:
    """Check Redis buses status."""
    import socket

    buses = {
        "system-redis": 6379,
        "market-redis": 6380,
        "intel-redis": 6381,
        "echo-redis": 6382,
    }

    results = {}
    for name, port in buses.items():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                running = s.connect_ex(('127.0.0.1', port)) == 0
                results[name] = {"port": port, "running": running}
        except Exception:
            results[name] = {"port": port, "running": False}

    return results


def check_truth() -> bool:
    """Check if truth is loaded in system-redis."""
    try:
        result = subprocess.run(
            ["redis-cli", "-h", "127.0.0.1", "-p", "6379", "EXISTS", "truth"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == "1"
    except Exception:
        return False


# ============================================================
# Health Monitoring System
# ============================================================

class HealthCollector:
    """
    Background daemon thread that collects system health every 30s.
    All Redis operations are READ-ONLY with 2s timeouts.
    Thread-safe via threading.Lock on all shared state.
    """

    REDIS_INSTANCES = {
        "system-redis": {"host": "127.0.0.1", "port": 6379},
        "market-redis": {"host": "127.0.0.1", "port": 6380},
        "intel-redis":  {"host": "127.0.0.1", "port": 6381},
        "echo-redis":   {"host": "127.0.0.1", "port": 6382},
    }

    HEARTBEAT_SERVICES = {
        "massive":        {"interval": 5,  "ttl": 15},
        "rss_agg":        {"interval": 5,  "ttl": 15},
        "vexy_ai":        {"interval": 15, "ttl": 45},
        "content_anal":   {"interval": 15, "ttl": 45},
        "journal":        {"interval": 5,  "ttl": 15},
        "copilot":        {"interval": 5,  "ttl": 15},
        "sse":            {"interval": 5,  "ttl": 15},
        "healer":         {"interval": 10, "ttl": 30},
        "mesh":           {"interval": 5,  "ttl": 15},
        "vexy_proxy":     {"interval": 10, "ttl": 30},
        "vexy_hydrator":  {"interval": 10, "ttl": 30},
    }

    HEALTH_ENDPOINTS = {
        "sse":             "http://127.0.0.1:3001/api/health",
        "journal":         "http://127.0.0.1:3002/health",
        "vexy_ai":         "http://127.0.0.1:3005/health",
        "vexy_proxy":      "http://127.0.0.1:3006/health",
        "vexy_hydrator":   "http://127.0.0.1:3007/health",
        "copilot":         "http://127.0.0.1:8095/health",
    }

    MAX_HISTORY = 240
    MAX_EVENTS = 100
    COLLECT_INTERVAL = 15

    def __init__(self):
        self._lock = threading.Lock()
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._events = deque(maxlen=self.MAX_EVENTS)
        self._latest = None
        self._previous_snapshot = None
        self._thread = None
        self._running = False
        self._webhook_url = ""
        self._webhook_timeout = 4

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._load_webhook_config()
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="health-collector"
        )
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_loop(self):
        # Brief startup delay so first collection has Redis ready
        time.sleep(5)
        while self._running:
            try:
                snapshot = self._collect()
                with self._lock:
                    self._latest = snapshot
                    self._history.append(snapshot)
                self._generate_events(snapshot)
            except Exception:
                pass
            time.sleep(self.COLLECT_INTERVAL)

    # ----------------------------------------------------------
    # Data Collection (all READ-ONLY)
    # ----------------------------------------------------------

    def _collect(self) -> dict:
        ts = time.time()
        redis_data = self._collect_redis()
        heartbeat_data = self._collect_heartbeats()
        http_data = self._collect_http_health()
        pid_data = self._collect_service_pids()

        # Merge PID status into heartbeat data: if a service is PID-alive
        # but heartbeat-dead, mark it as "running_no_heartbeat" instead of "dead"
        for svc, pid_info in pid_data.items():
            if svc in heartbeat_data:
                hb = heartbeat_data[svc]
                hb["pid_alive"] = pid_info.get("pid_alive", False)
                hb["pid"] = pid_info.get("pid")
                if not hb.get("alive") and pid_info.get("pid_alive"):
                    hb["status"] = "running_no_heartbeat"

        snapshot = {
            "ts": ts,
            "ts_iso": datetime.fromtimestamp(ts).isoformat(),
            "redis": redis_data,
            "heartbeats": heartbeat_data,
            "http_health": http_data,
            "score": 0.0,
        }
        snapshot["score"] = self._compute_score(snapshot)
        return snapshot

    def _collect_redis(self) -> dict:
        import redis
        results = {}
        for name, conn in self.REDIS_INSTANCES.items():
            try:
                r = redis.Redis(
                    host=conn["host"], port=conn["port"],
                    decode_responses=True,
                    socket_timeout=2, socket_connect_timeout=2,
                )
                info = r.info()
                dbsize = r.dbsize()
                hits = info.get("keyspace_hits", 0)
                misses = info.get("keyspace_misses", 0)
                total = hits + misses
                results[name] = {
                    "alive": True,
                    "used_memory_mb": round(info.get("used_memory", 0) / 1048576, 1),
                    "used_memory_peak_mb": round(info.get("used_memory_peak", 0) / 1048576, 1),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_keys": dbsize,
                    "uptime_seconds": info.get("uptime_in_seconds", 0),
                    "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                    "hit_rate": round(hits / total, 3) if total > 0 else 0.0,
                    "maxmemory": info.get("maxmemory", 0),
                    "evicted_keys": info.get("evicted_keys", 0),
                }
                r.close()
            except Exception:
                results[name] = {"alive": False}
        return results

    def _collect_heartbeats(self) -> dict:
        import redis
        results = {}
        try:
            r = redis.Redis(
                host="127.0.0.1", port=6379,
                decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2,
            )
            for svc, cfg in self.HEARTBEAT_SERVICES.items():
                key = f"{svc}:heartbeat"
                try:
                    data = r.get(key)
                    ttl = r.ttl(key)
                    if data:
                        payload = json.loads(data)
                        hb_ts = payload.get("ts", 0)
                        age = time.time() - hb_ts if hb_ts > 0 else None
                        # Degraded if TTL < 50% of expected
                        status = "healthy"
                        if ttl > 0 and ttl < cfg["ttl"] * 0.5:
                            status = "degraded"
                        results[svc] = {
                            "alive": True,
                            "last_ts": hb_ts,
                            "age_sec": round(age, 1) if age is not None else None,
                            "ttl_remaining": ttl if ttl > 0 else 0,
                            "expected_ttl": cfg["ttl"],
                            "status": status,
                        }
                    else:
                        results[svc] = {
                            "alive": False,
                            "status": "dead",
                            "expected_ttl": cfg["ttl"],
                        }
                except Exception:
                    results[svc] = {"alive": False, "status": "unknown"}
            r.close()
        except Exception:
            for svc in self.HEARTBEAT_SERVICES:
                results[svc] = {"alive": False, "status": "unknown"}
        return results

    def _collect_http_health(self) -> dict:
        import requests as req_lib
        results = {}
        for svc, url in self.HEALTH_ENDPOINTS.items():
            try:
                resp = req_lib.get(url, timeout=3)
                results[svc] = {
                    "reachable": True,
                    "status_code": resp.status_code,
                    "healthy": resp.ok,
                }
            except req_lib.exceptions.ConnectionError:
                results[svc] = {"reachable": False, "healthy": False, "error": "connection_refused"}
            except req_lib.exceptions.Timeout:
                results[svc] = {"reachable": False, "healthy": False, "error": "timeout"}
            except Exception as e:
                results[svc] = {"reachable": False, "healthy": False, "error": str(e)[:100]}
        return results

    def _collect_service_pids(self) -> dict:
        """
        Cross-reference heartbeat data with PID-based service status.
        Uses ServiceManager to check if processes are actually running,
        even when heartbeat threads have crashed.
        READ-ONLY: only reads PID files and checks process existence.
        """
        results = {}
        try:
            manager = ServiceManager()
            for svc_name in self.HEARTBEAT_SERVICES:
                if svc_name in SERVICES:
                    status = manager.get_status(svc_name)
                    results[svc_name] = {
                        "pid_alive": status.get("running", False),
                        "pid": status.get("pid"),
                    }
                else:
                    results[svc_name] = {"pid_alive": False, "pid": None}
        except Exception:
            pass
        return results

    # ----------------------------------------------------------
    # Health Score
    # ----------------------------------------------------------

    def _compute_score(self, snapshot: dict) -> float:
        redis_data = snapshot.get("redis", {})
        redis_count = len(self.REDIS_INSTANCES)
        redis_alive = sum(1 for v in redis_data.values() if v.get("alive"))
        redis_score = redis_alive / redis_count if redis_count > 0 else 0.0

        hb_data = snapshot.get("heartbeats", {})
        hb_count = len(self.HEARTBEAT_SERVICES)
        hb_sum = 0.0
        for info in hb_data.values():
            if info.get("status") == "healthy":
                hb_sum += 1.0
            elif info.get("status") == "degraded":
                hb_sum += 0.5
            elif info.get("status") == "running_no_heartbeat":
                # PID alive but heartbeat thread dead — partial credit
                hb_sum += 0.5
        hb_score = hb_sum / hb_count if hb_count > 0 else 0.0

        http_data = snapshot.get("http_health", {})
        http_count = len(self.HEALTH_ENDPOINTS)
        http_healthy = sum(1 for v in http_data.values() if v.get("healthy"))
        http_score = http_healthy / http_count if http_count > 0 else 0.0

        return round(redis_score * 0.30 + hb_score * 0.50 + http_score * 0.20, 3)

    # ----------------------------------------------------------
    # Event Generation & Notifications
    # ----------------------------------------------------------

    def _generate_events(self, snapshot: dict):
        """Compare current snapshot with previous to detect meaningful events."""
        prev = self._previous_snapshot
        events = []
        ts = snapshot["ts"]
        ts_iso = snapshot["ts_iso"]

        if prev is not None:
            self._detect_service_events(events, snapshot, prev, ts, ts_iso)
            self._detect_redis_events(events, snapshot, prev, ts, ts_iso)
            self._detect_http_events(events, snapshot, prev, ts, ts_iso)
            self._detect_score_events(events, snapshot, prev, ts, ts_iso)

        if events:
            with self._lock:
                for ev in events:
                    self._events.append(ev)
            for ev in events:
                self._fire_webhook_event(ev)

            # Trigger auto-healer for service_down events
            for ev in events:
                if ev["type"] == "service_down" and _auto_healer.enabled:
                    _auto_healer.trigger(ev["service"], ev, snapshot)

        self._previous_snapshot = snapshot

    def _detect_service_events(self, events, snap, prev, ts, ts_iso):
        hb_data = snap.get("heartbeats", {})
        prev_hb = prev.get("heartbeats", {})

        for svc, info in hb_data.items():
            new_status = info.get("status", "unknown")
            old_info = prev_hb.get(svc, {})
            old_status = old_info.get("status")
            if old_status is None or old_status == new_status:
                continue

            pid = info.get("pid", "?")
            pid_alive = info.get("pid_alive", False)

            if new_status == "dead" and not pid_alive:
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "service_down", "severity": "critical",
                    "service": svc,
                    "message": f"{svc} crashed — heartbeat dead, process gone (was {old_status})",
                    "data": {"from": old_status, "pid_alive": False},
                })
            elif new_status in ("dead", "running_no_heartbeat") and pid_alive and old_status in ("healthy", "degraded"):
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "heartbeat_lost", "severity": "warning",
                    "service": svc,
                    "message": f"{svc} heartbeat thread died — PID {pid} still running (was {old_status})",
                    "data": {"from": old_status, "pid": pid},
                })
            elif new_status == "healthy" and old_status == "running_no_heartbeat":
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "heartbeat_restored", "severity": "info",
                    "service": svc,
                    "message": f"{svc} heartbeat restored (was running without heartbeat)",
                    "data": {"from": old_status},
                })
            elif new_status == "healthy" and old_status == "dead":
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "service_recovered", "severity": "info",
                    "service": svc,
                    "message": f"{svc} recovered — heartbeat healthy, PID {pid}",
                    "data": {"from": old_status, "pid": pid},
                })
            elif new_status == "degraded" and old_status == "healthy":
                ttl = info.get("ttl_remaining", 0)
                expected = info.get("expected_ttl", 0)
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "service_degraded", "severity": "warning",
                    "service": svc,
                    "message": f"{svc} degraded — TTL {ttl}s remaining (expected {expected}s)",
                    "data": {"ttl_remaining": ttl, "expected_ttl": expected},
                })

    def _detect_redis_events(self, events, snap, prev, ts, ts_iso):
        redis_data = snap.get("redis", {})
        prev_redis = prev.get("redis", {})

        for name, info in redis_data.items():
            old_info = prev_redis.get(name, {})
            alive_now = info.get("alive", False)
            alive_before = old_info.get("alive")
            if alive_before is None:
                continue

            if alive_before and not alive_now:
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "redis_down", "severity": "critical",
                    "service": name,
                    "message": f"{name} is unreachable",
                    "data": {},
                })
            elif not alive_before and alive_now:
                mem = info.get("used_memory_mb", 0)
                keys = info.get("total_keys", 0)
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "redis_recovered", "severity": "info",
                    "service": name,
                    "message": f"{name} recovered — {mem}MB, {keys:,} keys",
                    "data": {"used_memory_mb": mem, "total_keys": keys},
                })

            # Metric comparisons (both cycles alive)
            if alive_now and alive_before:
                mem_now = info.get("used_memory_mb", 0)
                mem_prev = old_info.get("used_memory_mb", 0)
                delta_mb = mem_now - mem_prev
                if mem_prev > 0 and delta_mb > 0:
                    pct = delta_mb / mem_prev
                    # Only alert if >50% spike AND absolute jump > 500MB
                    if pct > 0.50 and delta_mb > 500:
                        events.append({
                            "ts": ts, "ts_iso": ts_iso,
                            "type": "redis_memory_warning", "severity": "warning",
                            "service": name,
                            "message": f"{name} memory spike: {mem_now:.0f}MB (+{pct*100:.0f}%, +{delta_mb:.0f}MB in {self.COLLECT_INTERVAL}s, was {mem_prev:.0f}MB)",
                            "data": {"used_memory_mb": mem_now, "previous_mb": mem_prev, "pct_change": round(pct, 3)},
                        })
                if mem_now > 2000 and mem_prev <= 2000:
                    events.append({
                        "ts": ts, "ts_iso": ts_iso,
                        "type": "redis_memory_warning", "severity": "warning",
                        "service": name,
                        "message": f"{name} crossed 2GB threshold: {mem_now:.0f}MB",
                        "data": {"used_memory_mb": mem_now, "threshold_mb": 2000},
                    })

                clients_now = info.get("connected_clients", 0)
                clients_prev = old_info.get("connected_clients", 0)
                if clients_prev > 0:
                    change = (clients_now - clients_prev) / clients_prev
                    if change > 0.50:
                        events.append({
                            "ts": ts, "ts_iso": ts_iso,
                            "type": "redis_clients_spike", "severity": "warning",
                            "service": name,
                            "message": f"{name} client spike: {clients_now} (+{change*100:.0f}%, was {clients_prev})",
                            "data": {"connected_clients": clients_now, "previous": clients_prev},
                        })

    def _detect_http_events(self, events, snap, prev, ts, ts_iso):
        http_data = snap.get("http_health", {})
        prev_http = prev.get("http_health", {})

        for svc, info in http_data.items():
            old_info = prev_http.get(svc, {})
            reachable_now = info.get("reachable", False)
            healthy_now = info.get("healthy", False)
            reachable_before = old_info.get("reachable")
            if reachable_before is None:
                continue

            if reachable_before and not reachable_now:
                err = info.get("error", "unknown")
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "endpoint_down", "severity": "critical",
                    "service": svc,
                    "message": f"{svc} HTTP endpoint down ({err})",
                    "data": {"error": err},
                })
            elif not reachable_before and reachable_now and healthy_now:
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "endpoint_recovered", "severity": "info",
                    "service": svc,
                    "message": f"{svc} HTTP endpoint recovered (status {info.get('status_code', '?')})",
                    "data": {"status_code": info.get("status_code")},
                })
            elif reachable_now and not healthy_now and old_info.get("healthy", True):
                code = info.get("status_code", "?")
                events.append({
                    "ts": ts, "ts_iso": ts_iso,
                    "type": "endpoint_unhealthy", "severity": "warning",
                    "service": svc,
                    "message": f"{svc} returning HTTP {code}",
                    "data": {"status_code": code},
                })

    def _detect_score_events(self, events, snap, prev, ts, ts_iso):
        score_now = snap.get("score", 0.0)
        score_prev = prev.get("score")
        if score_prev is None:
            return

        if score_now < 0.60 and score_prev >= 0.60:
            events.append({
                "ts": ts, "ts_iso": ts_iso,
                "type": "score_critical", "severity": "critical",
                "service": None,
                "message": f"Health score dropped to {score_now*100:.0f}% (was {score_prev*100:.0f}%)",
                "data": {"score": score_now, "previous_score": score_prev},
            })
        elif score_now >= 0.80 and score_prev < 0.80:
            events.append({
                "ts": ts, "ts_iso": ts_iso,
                "type": "score_recovered", "severity": "info",
                "service": None,
                "message": f"Health score recovered to {score_now*100:.0f}% (was {score_prev*100:.0f}%)",
                "data": {"score": score_now, "previous_score": score_prev},
            })

    def _extract_crash_logs(self, svc: str) -> str:
        """
        Extract meaningful log context for a crashed/degraded service.
        Reads last 100 lines, finds the last run's operational output,
        and prioritizes error lines over startup boilerplate.
        """
        mgr = ServiceManager()
        log_data = mgr.logs(svc, lines=100)
        raw = log_data.get("logs", "").strip()
        if not raw:
            return ""

        lines = raw.split("\n")

        # Find all "Starting" headers to identify run boundaries
        start_indices = []
        for i, line in enumerate(lines):
            if line.startswith("Starting ") and "at 20" in line:
                start_indices.append(i)

        def _lines_after_header(header_idx):
            """Get operational lines after a startup header block."""
            run_start = header_idx
            while run_start < len(lines) and (
                lines[run_start].startswith("=") or
                lines[run_start].startswith("Starting ") or
                lines[run_start].startswith("Command: ") or
                lines[run_start].strip() == ""
            ):
                run_start += 1
            return lines[run_start:]

        # Get lines from the most recent run
        if start_indices:
            run_lines = _lines_after_header(start_indices[-1])
            # If current run has almost nothing useful, also grab previous run's tail
            if len(run_lines) < 5 and len(start_indices) >= 2:
                prev_header = start_indices[-2]
                curr_header = start_indices[-1]
                prev_run = lines[prev_header:curr_header]
                # Get the last 20 lines of the previous run
                prev_tail = [l for l in prev_run if not l.startswith("=") and l.strip()]
                if prev_tail:
                    run_lines = prev_tail[-20:] + ["", "--- service restarted ---", ""] + run_lines
        else:
            run_lines = lines

        # Extract error/exception lines if any exist
        error_lines = []
        for i, line in enumerate(run_lines):
            lower = line.lower()
            if any(kw in lower for kw in ["error", "exception", "traceback", "fatal", "critical", "failed", "crash"]):
                # Grab context: 2 lines before + the error + 3 lines after
                start = max(0, i - 2)
                end = min(len(run_lines), i + 4)
                for ctx_line in run_lines[start:end]:
                    if ctx_line not in error_lines:
                        error_lines.append(ctx_line)

        if error_lines:
            # Show errors with context, plus last 5 operational lines
            result_lines = error_lines
            tail = run_lines[-5:]
            if tail and tail != error_lines[-5:]:
                result_lines.append("...")
                result_lines.extend(tail)
        else:
            # No errors found — show last 20 operational lines (skip startup noise)
            # Filter out common startup boilerplate
            startup_noise = [
                "starting setup", "loading truth", "truth loaded", "parsing component",
                "loaded structural", "setup complete", "log configured",
                "configuration loaded", "heartbeat thread started",
                "entering service loop", "orchestrator start", "ctrl+c",
                "starting orchestrator", "service loop", "main loop",
            ]
            operational = [l for l in run_lines if not any(
                kw in l.lower() for kw in startup_noise
            )]
            if operational:
                result_lines = operational[-20:]
            elif run_lines:
                # Only startup lines exist — service had no operational output
                return "(service had no operational output before shutdown — only startup logs)"
            else:
                result_lines = []

        result = "\n".join(result_lines).strip()
        # Slack block text limit ~3000 chars
        if len(result) > 2800:
            result = result[-2800:]
        return result if result else "(no operational output before shutdown)"

    def _fire_webhook_event(self, event: dict):
        url = self._webhook_url
        if not url:
            return
        try:
            severity = event["severity"]
            svc = event.get("service") or "system"
            ev_type = event.get("type", "unknown")
            ts_iso = event.get("ts_iso", "")

            # Severity header
            if severity == "critical":
                header = f":red_circle: CRITICAL — {svc}"
            elif severity == "warning":
                header = f":warning: WARNING — {svc}"
            else:
                header = f":large_green_circle: RECOVERED — {svc}"

            # Build context fields
            fields = []

            # Health score context
            latest = self.get_latest()
            if latest:
                score = latest.get("score", 0)
                label = _score_label(score)
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*Health Score:* {score*100:.0f}% ({label})"
                })

            fields.append({"type": "mrkdwn", "text": f"*Event:* `{ev_type}`"})
            fields.append({"type": "mrkdwn", "text": f"*Time:* {ts_iso}"})

            # Add relevant metrics from event data
            data = event.get("data", {})
            if data.get("used_memory_mb"):
                prev = data.get("previous_mb", "?")
                fields.append({"type": "mrkdwn", "text": f"*Memory:* {data['used_memory_mb']}MB (was {prev}MB)"})
            if data.get("ttl_remaining") is not None:
                fields.append({"type": "mrkdwn", "text": f"*TTL:* {data['ttl_remaining']}s / {data.get('expected_ttl', '?')}s"})

            # Build Slack Block Kit payload
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": header}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{event['message']}*"}},
            ]

            if fields:
                blocks.append({"type": "section", "fields": fields[:8]})

            # Include recent logs for service events
            if svc != "system" and ev_type in ("service_down", "service_degraded", "heartbeat_lost", "endpoint_down"):
                try:
                    log_text = self._extract_crash_logs(svc)
                    if log_text:
                        blocks.append({"type": "divider"})
                        blocks.append({
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*Recent Logs ({svc}):*\n```{log_text}```"}
                        })
                except Exception:
                    pass

            # Redis summary for Redis events
            if ev_type.startswith("redis_") and latest:
                redis_info = latest.get("redis", {}).get(svc, {})
                if redis_info.get("alive"):
                    mem = redis_info.get("used_memory_mb", 0)
                    keys = redis_info.get("total_keys", 0)
                    ops = redis_info.get("ops_per_sec", 0)
                    clients = redis_info.get("connected_clients", 0)
                    blocks.append({"type": "divider"})
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{svc} Stats:* {mem}MB mem | {keys:,} keys | {ops} ops/s | {clients} clients"}
                    })

            payload = json.dumps({
                "text": f"{header}: {event['message']}",
                "blocks": blocks,
            }).encode()

            req = urllib_request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib_request.urlopen(req, timeout=self._webhook_timeout)
        except Exception:
            pass

    # ----------------------------------------------------------
    # Thread-safe Accessors (called by API endpoints)
    # ----------------------------------------------------------

    def get_latest(self) -> dict:
        with self._lock:
            return dict(self._latest) if self._latest else {}

    def get_history(self, count: int = 240) -> list:
        with self._lock:
            items = list(self._history)
        return items[-count:]

    def get_alerts(self, count: int = 100) -> list:
        """Backwards-compatible: returns events."""
        with self._lock:
            return list(self._events)[-count:]

    def get_events(self, count: int = 100, severity: str = None) -> list:
        """Get events with optional severity filter (comma-separated)."""
        with self._lock:
            items = list(self._events)
        if severity:
            allowed = set(s.strip() for s in severity.split(","))
            items = [e for e in items if e.get("severity") in allowed]
        return items[-count:]

    def configure_webhook(self, url: str, timeout: int = 4):
        self._webhook_url = url
        self._webhook_timeout = timeout
        # Persist to config file
        try:
            cfg = load_admin_config()
            cfg["health_webhook"] = {"url": url, "timeout": timeout}
            save_admin_config(cfg)
        except Exception:
            pass

    def _load_webhook_config(self):
        """Load webhook URL from persistent config on startup."""
        try:
            cfg = load_admin_config()
            wh = cfg.get("health_webhook", {})
            if wh.get("url"):
                self._webhook_url = wh["url"]
                self._webhook_timeout = wh.get("timeout", 4)
        except Exception:
            pass

    def get_webhook_config(self) -> dict:
        return {"url": self._webhook_url, "timeout": self._webhook_timeout}


# ============================================================
# AutoHealer — AI-powered service recovery via Claude Code CLI
# ============================================================

class AutoHealer:
    """Two-phase auto-healing: diagnose (read-only) then fix (guarded edits).

    Phase 1: Read-only diagnosis — determines what went wrong and if it can be safely fixed
    Phase 2: Guarded fix — applies minimal code changes with git stash rollback safety net

    Guardrails:
    - Phase 1 is strictly read-only (Read, Glob, Grep only)
    - Phase 2 edits restricted to services/{service}/ directory only
    - Git stash before edits, auto-rollback if fix fails
    - 60-second health verification after fix
    - 10-minute cooldown per service (no retry spam)
    - 3-minute timeout per Claude subprocess
    - $2 budget for diagnosis, $3 budget for fix ($5 total max)
    - Slack notifications at every stage
    """

    CLAUDE_PATH = "/opt/homebrew/bin/claude"
    COOLDOWN_SEC = 600       # 10 minutes between attempts per service
    TIMEOUT_SEC = 180        # 3-minute subprocess timeout
    VERIFY_TIMEOUT = 60      # 60 seconds to verify health after fix
    DIAG_BUDGET = 2          # $2 for diagnosis phase
    FIX_BUDGET = 3           # $3 for fix phase

    DIAGNOSIS_PROMPT = """You are a diagnostic agent for MarketSwarm, a trading analytics platform.
A service has crashed. Your job is to investigate and determine if it can be safely fixed.

RULES:
1. Read the service's log file first to understand what happened
2. Scan the service's code directory to understand the codebase
3. Check if the issue is in the service's own code or in shared dependencies
4. Produce your analysis as a JSON object (and ONLY the JSON, no other text)

OUTPUT FORMAT (JSON only):
{{
  "diagnosis": "Clear explanation of what went wrong",
  "root_cause": "The specific root cause",
  "can_fix": true or false,
  "risk_level": "low or medium or high",
  "fix_plan": "Step-by-step plan for the fix (if can_fix is true)",
  "affected_files": ["list of files that would need to change"],
  "reason_cannot_fix": "Explanation if can_fix is false"
}}

Set can_fix to false if ANY of these apply:
- The fix requires changing files outside services/{service}/
- The fix requires changing shared/ code, scripts/, truth/, or ui/
- The fix requires changing environment variables or Redis configuration
- The root cause is in a dependency, not the service's own code
- The fix could affect other running services
- You are not confident the fix will work
- The issue is a transient network/resource error (just needs restart)
- The issue is an OOM, disk full, or hardware/resource issue"""

    FIX_PROMPT = """You are a repair agent for MarketSwarm. You have been authorized to fix a specific issue.

HARD RULES — VIOLATION WILL CAUSE SYSTEM DAMAGE:
1. ONLY edit files inside services/{service}/ — NO exceptions
2. NEVER create files outside services/{service}/
3. NEVER modify shared/, scripts/, truth/, ui/, or any other service directory
4. Make the MINIMAL change needed — do not refactor, clean up, or improve
5. Do not change any API contracts, function signatures, or data formats
6. Do not add new dependencies

After making changes, output ONLY a JSON summary:
{{
  "files_changed": ["list of modified files"],
  "description": "What was changed and why",
  "changes_made": "Technical summary of edits"
}}"""

    def __init__(self, health_collector):
        self._hc = health_collector
        self._cooldowns: Dict[str, float] = {}
        self._active: Optional[str] = None
        self._lock = threading.Lock()
        self._log_file = ROOT / "logs" / "healer.log"
        self._enabled = False  # Off by default — enable via UI toggle
        self._history: deque = deque(maxlen=50)  # recent heal attempts

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val
        self._log(f"AutoHealer {'enabled' if val else 'disabled'}")

    def trigger(self, service_name: str, event: dict, snapshot: dict):
        """Entry point — called from _generate_events() on service_down."""
        with self._lock:
            if not self._enabled:
                return
            # Check cooldown
            last = self._cooldowns.get(service_name, 0)
            if time.time() - last < self.COOLDOWN_SEC:
                remaining = int(self.COOLDOWN_SEC - (time.time() - last))
                self._log(f"Skipping {service_name} — cooldown ({remaining}s remaining)")
                return
            # Check not already healing
            if self._active:
                self._log(f"Skipping {service_name} — already healing {self._active}")
                return
            self._active = service_name
            self._cooldowns[service_name] = time.time()

        t = threading.Thread(
            target=self._heal_thread,
            args=(service_name, event, snapshot),
            daemon=True,
            name=f"healer-{service_name}",
        )
        t.start()

    def _heal_thread(self, service_name: str, event: dict, snapshot: dict):
        """Full two-phase healing flow."""
        record = {
            "service": service_name,
            "started": datetime.now().isoformat(),
            "trigger_event": event.get("type", "unknown"),
            "phases": {},
            "result": "pending",
        }
        try:
            self._log(f"=== HEAL START: {service_name} ===")
            self._slack_notify(
                f":mag: INVESTIGATING — {service_name}",
                f"{service_name} crashed — starting AI diagnosis",
                "warning",
            )

            # Phase 1: Diagnosis (read-only)
            self._log(f"Phase 1: Diagnosing {service_name}...")
            diagnosis = self._phase1_diagnose(service_name, snapshot)
            record["phases"]["diagnosis"] = diagnosis

            if diagnosis is None:
                record["result"] = "diagnosis_failed"
                self._slack_notify(
                    f":x: DIAGNOSIS FAILED — {service_name}",
                    "Claude CLI failed to produce a diagnosis. Manual intervention needed.",
                    "critical",
                )
                return

            self._log(f"Diagnosis: can_fix={diagnosis.get('can_fix')}, risk={diagnosis.get('risk_level')}")

            # Check if fixable
            if not diagnosis.get("can_fix", False) or diagnosis.get("risk_level") == "high":
                record["result"] = "cannot_fix"
                reason = diagnosis.get("reason_cannot_fix") or diagnosis.get("diagnosis", "Unknown")
                self._slack_notify(
                    f":no_entry: AI CANNOT FIX — {service_name}",
                    f"*Diagnosis:* {diagnosis.get('diagnosis', 'N/A')}\n"
                    f"*Risk Level:* {diagnosis.get('risk_level', 'N/A')}\n"
                    f"*Reason:* {reason}\n"
                    f"*Action Required:* Manual intervention needed",
                    "critical",
                )
                return

            # Phase 2: Fix (guarded edits)
            self._log(f"Phase 2: Applying fix for {service_name}...")
            self._slack_notify(
                f":wrench: APPLYING FIX — {service_name}",
                f"*Diagnosis:* {diagnosis.get('diagnosis', 'N/A')}\n"
                f"*Fix Plan:* {diagnosis.get('fix_plan', 'N/A')}",
                "warning",
            )

            fix_result = self._phase2_fix(service_name, diagnosis)
            record["phases"]["fix"] = fix_result

            if fix_result is None:
                record["result"] = "fix_failed"
                self._rollback_stash(service_name)
                self._slack_notify(
                    f":x: FIX FAILED — {service_name}",
                    "Claude CLI failed to apply fixes. Changes rolled back. Manual intervention needed.",
                    "critical",
                )
                return

            # Verify: restart and check health
            self._log(f"Verifying fix for {service_name}...")
            healthy = self._verify_health(service_name)

            if healthy:
                record["result"] = "healed"
                self._drop_stash()
                files = fix_result.get("files_changed", [])
                self._slack_notify(
                    f":white_check_mark: AUTO-HEALED — {service_name}",
                    f"*Diagnosis:* {diagnosis.get('diagnosis', 'N/A')}\n"
                    f"*Fix:* {fix_result.get('description', 'N/A')}\n"
                    f"*Files Changed:* {', '.join(files) if files else 'N/A'}\n"
                    f"*Verified:* Service healthy, heartbeat active",
                    "info",
                )
            else:
                record["result"] = "verify_failed"
                self._rollback_stash(service_name)
                self._slack_notify(
                    f":x: FIX FAILED — {service_name}",
                    f"*Diagnosis:* {diagnosis.get('diagnosis', 'N/A')}\n"
                    f"*Attempted Fix:* {fix_result.get('description', 'N/A')}\n"
                    f"*Result:* Service did not recover — changes rolled back\n"
                    f"*Action Required:* Manual intervention needed",
                    "critical",
                )

        except Exception as exc:
            record["result"] = "error"
            record["error"] = str(exc)
            self._log(f"ERROR healing {service_name}: {exc}")
            self._slack_notify(
                f":x: HEALER ERROR — {service_name}",
                f"Unexpected error: {exc}\nManual intervention needed.",
                "critical",
            )
        finally:
            record["finished"] = datetime.now().isoformat()
            with self._lock:
                self._active = None
                self._history.append(record)
            self._log(f"=== HEAL END: {service_name} — {record['result']} ===")

    def _load_context_doc(self) -> str:
        """Load the healer context document."""
        ctx_path = ROOT / "docs" / "healer-context.md"
        try:
            return ctx_path.read_text() if ctx_path.exists() else ""
        except Exception:
            return ""

    def _read_log_tail(self, service_name: str, lines: int = 200) -> str:
        """Read the last N lines of a service's log file."""
        log_path = ROOT / "logs" / f"{service_name}.log"
        try:
            if not log_path.exists():
                return "(no log file found)"
            text = log_path.read_text()
            all_lines = text.strip().split("\n")
            return "\n".join(all_lines[-lines:])
        except Exception:
            return "(failed to read log)"

    def _format_health_snapshot(self, snapshot: dict) -> str:
        """Format health snapshot into a readable summary for Claude."""
        parts = []
        # Redis status
        redis_info = snapshot.get("redis", {})
        redis_lines = []
        for name, info in redis_info.items():
            if isinstance(info, dict):
                status = "UP" if info.get("alive") else "DOWN"
                mem = info.get("used_memory_mb", "?")
                redis_lines.append(f"  {name}: {status} ({mem} MB)")
        if redis_lines:
            parts.append("Redis Instances:")
            parts.extend(redis_lines)

        # Heartbeat + PID status (both live in heartbeats dict)
        hb_info = snapshot.get("heartbeats", {})
        alive = []
        dead = []
        pid_lines = []
        for svc, info in hb_info.items():
            if isinstance(info, dict):
                if info.get("alive"):
                    alive.append(svc)
                else:
                    dead.append(svc)
                pid = info.get("pid", "?")
                pid_alive = info.get("pid_alive", False)
                pid_lines.append(f"  {svc}: PID {pid} ({'running' if pid_alive else 'stopped'})")
        parts.append(f"\nHeartbeats Alive: {', '.join(alive) if alive else 'none'}")
        if dead:
            parts.append(f"Heartbeats Dead: {', '.join(dead)}")

        if pid_lines:
            parts.append("\nService PIDs:")
            parts.extend(pid_lines)

        return "\n".join(parts) if parts else "(no health data)"

    @staticmethod
    def _clean_env() -> dict:
        """Return env dict with CLAUDECODE vars stripped so nested CLI works."""
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("CLAUDECODE"):
                del env[key]
        return env

    def _phase1_diagnose(self, service_name: str, snapshot: dict) -> Optional[dict]:
        """Phase 1: Read-only diagnosis via Claude CLI."""
        svc_dir = ROOT / "services" / service_name

        # Pre-load context, logs, and health data
        context_doc = self._load_context_doc()
        log_excerpt = self._read_log_tail(service_name, 200)
        health_summary = self._format_health_snapshot(snapshot)

        prompt = (
            f"=== MARKETSWARM SYSTEM CONTEXT ===\n{context_doc}\n\n"
            f"=== SERVICE LOG (last 200 lines of logs/{service_name}.log) ===\n{log_excerpt}\n\n"
            f"=== HEALTH SNAPSHOT ===\n{health_summary}\n\n"
            f"A MarketSwarm service named '{service_name}' has crashed.\n"
            f"Service code directory: {svc_dir}\n"
            f"Project root: {ROOT}\n\n"
            f"The system context, log, and health snapshot are provided above.\n"
            f"Investigate the crash — scan the service code if needed to understand the bug.\n"
            f"Remember: output ONLY valid JSON, no markdown fences, no extra text."
        )

        sys_prompt = self.DIAGNOSIS_PROMPT.replace("{service}", service_name)

        try:
            result = subprocess.run(
                [
                    self.CLAUDE_PATH,
                    "--print",
                    "--output-format", "json",
                    "--model", "sonnet",
                    "--system-prompt", sys_prompt,
                    "--allowedTools", "Read,Glob,Grep",
                    "--max-budget-usd", str(self.DIAG_BUDGET),
                    "--no-session-persistence",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SEC,
                cwd=str(ROOT),
                env=self._clean_env(),
            )

            if result.returncode != 0:
                self._log(f"Phase 1 CLI error (rc={result.returncode}): {result.stderr[:500]}")
                return None

            return self._parse_claude_json(result.stdout, "diagnosis")

        except subprocess.TimeoutExpired:
            self._log(f"Phase 1 timed out after {self.TIMEOUT_SEC}s")
            return None
        except Exception as exc:
            self._log(f"Phase 1 error: {exc}")
            return None

    def _phase2_fix(self, service_name: str, diagnosis: dict) -> Optional[dict]:
        """Phase 2: Apply fix with git stash safety net."""
        svc_dir = ROOT / "services" / service_name

        # Git stash scoped to service directory
        self._create_stash(service_name)

        prompt = (
            f"You are fixing a bug in the MarketSwarm service '{service_name}'.\n\n"
            f"Service directory: {svc_dir}\n"
            f"Project root: {ROOT}\n\n"
            f"DIAGNOSIS:\n{diagnosis.get('diagnosis', 'N/A')}\n\n"
            f"ROOT CAUSE:\n{diagnosis.get('root_cause', 'N/A')}\n\n"
            f"FIX PLAN:\n{diagnosis.get('fix_plan', 'N/A')}\n\n"
            f"AFFECTED FILES:\n{json.dumps(diagnosis.get('affected_files', []))}\n\n"
            f"Apply the fix now. ONLY edit files inside services/{service_name}/.\n"
            f"Output ONLY valid JSON when done, no markdown fences, no extra text."
        )

        # Include system context so Claude understands conventions
        context_doc = self._load_context_doc()
        sys_prompt = (
            f"=== MARKETSWARM SYSTEM CONTEXT ===\n{context_doc}\n\n"
            f"{self.FIX_PROMPT.replace('{service}', service_name)}"
        ) if context_doc else self.FIX_PROMPT.replace("{service}", service_name)

        try:
            result = subprocess.run(
                [
                    self.CLAUDE_PATH,
                    "--print",
                    "--output-format", "json",
                    "--model", "sonnet",
                    "--system-prompt", sys_prompt,
                    "--allowedTools", "Read,Glob,Grep,Edit,Write",
                    "--disallowedTools", "Bash",
                    "--max-budget-usd", str(self.FIX_BUDGET),
                    "--no-session-persistence",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SEC,
                cwd=str(ROOT),
                env=self._clean_env(),
            )

            if result.returncode != 0:
                self._log(f"Phase 2 CLI error (rc={result.returncode}): {result.stderr[:500]}")
                return None

            return self._parse_claude_json(result.stdout, "fix")

        except subprocess.TimeoutExpired:
            self._log(f"Phase 2 timed out after {self.TIMEOUT_SEC}s")
            return None
        except Exception as exc:
            self._log(f"Phase 2 error: {exc}")
            return None

    def _verify_health(self, service_name: str) -> bool:
        """Restart service and verify it becomes healthy within VERIFY_TIMEOUT."""
        try:
            mgr = ServiceManager()
            mgr.restart(service_name)
            self._log(f"Restarted {service_name}, waiting for health verification...")

            deadline = time.time() + self.VERIFY_TIMEOUT
            while time.time() < deadline:
                time.sleep(5)
                status = mgr.get_status(service_name)
                pid = status.get("pid")
                running = status.get("running", False)

                if not running:
                    continue

                # Also check heartbeat via Redis
                try:
                    import redis as redis_lib
                    r = redis_lib.Redis(host="127.0.0.1", port=6379, decode_responses=True)
                    hb_key = f"{service_name}:heartbeat"
                    if r.exists(hb_key):
                        self._log(f"Verified: {service_name} PID={pid}, heartbeat alive")
                        r.close()
                        return True
                    r.close()
                except Exception:
                    pass

                self._log(f"Waiting... {service_name} running={running}, pid={pid}")

            self._log(f"Verification timed out after {self.VERIFY_TIMEOUT}s")
            return False

        except Exception as exc:
            self._log(f"Verification error: {exc}")
            return False

    def _create_stash(self, service_name: str):
        """Git stash scoped to service directory."""
        try:
            ts = int(time.time())
            subprocess.run(
                ["git", "stash", "push", "-m", f"healer-{service_name}-{ts}",
                 "--", f"services/{service_name}/"],
                capture_output=True, text=True, cwd=str(ROOT), timeout=10,
            )
            self._log(f"Created git stash for services/{service_name}/")
        except Exception as exc:
            self._log(f"Git stash create warning: {exc}")

    def _rollback_stash(self, service_name: str):
        """Pop the most recent stash to rollback changes."""
        try:
            result = subprocess.run(
                ["git", "stash", "pop"],
                capture_output=True, text=True, cwd=str(ROOT), timeout=10,
            )
            if result.returncode == 0:
                self._log(f"Rolled back changes for {service_name}")
            else:
                self._log(f"Git stash pop warning: {result.stderr[:200]}")
        except Exception as exc:
            self._log(f"Git stash pop error: {exc}")

    def _drop_stash(self):
        """Drop the most recent stash (fix was successful)."""
        try:
            subprocess.run(
                ["git", "stash", "drop"],
                capture_output=True, text=True, cwd=str(ROOT), timeout=10,
            )
        except Exception:
            pass

    def _parse_claude_json(self, output: str, phase: str) -> Optional[dict]:
        """Parse JSON from Claude CLI output (handles --output-format json wrapper)."""
        try:
            # --output-format json wraps response in {"result": "...", ...}
            wrapper = json.loads(output)
            content = wrapper.get("result", "")
            if isinstance(content, dict):
                return content

            # Try to extract JSON from the text content
            text = str(content)

            # Strip markdown fences if present
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]

            return json.loads(text.strip())
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            self._log(f"Failed to parse {phase} JSON: {exc}")
            self._log(f"Raw output (first 500 chars): {output[:500]}")
            return None

    def _slack_notify(self, header: str, body: str, severity: str):
        """Send Slack notification via HealthCollector's webhook."""
        url = self._hc._webhook_url
        if not url:
            return
        try:
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
                {"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}},
            ]
            # Add health score context
            latest = self._hc.get_latest()
            if latest:
                score = latest.get("score", 0)
                label = _score_label(score)
                blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"Health Score: {score*100:.0f}% ({label}) | AutoHealer"}],
                })

            payload = json.dumps({
                "text": f"{header}: {body[:200]}",
                "blocks": blocks,
            }).encode()

            req = urllib_request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib_request.urlopen(req, timeout=4)
        except Exception as exc:
            self._log(f"Slack notify error: {exc}")

    def _log(self, message: str):
        """Append timestamped line to healer log file."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "a") as f:
                f.write(line)
        except Exception:
            pass

    # Thread-safe accessors for API

    def get_status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "active": self._active,
                "cooldowns": {
                    svc: {
                        "last_attempt": datetime.fromtimestamp(ts).isoformat(),
                        "remaining_sec": max(0, int(self.COOLDOWN_SEC - (time.time() - ts))),
                    }
                    for svc, ts in self._cooldowns.items()
                },
                "history": list(self._history),
            }

    def get_log(self, lines: int = 100) -> str:
        try:
            if not self._log_file.exists():
                return "(no healer log yet)"
            text = self._log_file.read_text()
            all_lines = text.strip().split("\n")
            return "\n".join(all_lines[-lines:])
        except Exception:
            return "(error reading healer log)"


def _score_label(score: float) -> str:
    if score >= 0.95:
        return "excellent"
    if score >= 0.80:
        return "good"
    if score >= 0.60:
        return "degraded"
    if score >= 0.30:
        return "critical"
    return "down"


# Module-level singletons (started in create_web_app)
_health_collector = HealthCollector()
_auto_healer = AutoHealer(_health_collector)


# ============================================================
# Web UI Server (FastAPI)
# ============================================================

def create_web_app():
    """Create and configure the FastAPI web application."""
    from fastapi import FastAPI, HTTPException, Body
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    from typing import Optional

    app = FastAPI(title="MarketSwarm Node Admin", version="1.0.0")

    # Enable CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        """Serve the dashboard HTML."""
        html_path = ADMIN_UI_DIR / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text())
        return HTMLResponse(content="<h1>Admin UI not found</h1>", status_code=404)

    @app.get("/styles.css")
    def styles():
        """Serve the CSS file."""
        css_path = ADMIN_UI_DIR / "styles.css"
        if css_path.exists():
            return FileResponse(css_path, media_type="text/css")
        raise HTTPException(status_code=404, detail="CSS not found")

    @app.get("/app.js")
    def javascript():
        """Serve the JavaScript file."""
        js_path = ADMIN_UI_DIR / "app.js"
        if js_path.exists():
            return FileResponse(js_path, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="JS not found")

    @app.get("/api/admin/info")
    def api_admin_info():
        """Get admin server version and capabilities."""
        return {
            "version": ADMIN_VERSION,
            "build_date": ADMIN_BUILD_DATE,
            "features": ADMIN_FEATURES,
            "config_file": str(CONFIG_FILE),
            "admin_ui_dir": str(ADMIN_UI_DIR),
        }

    @app.get("/api/status")
    def api_status():
        """Get status of all services, Redis buses, and truth."""
        manager = ServiceManager()

        # Get node info from truth.json
        node_info = {"name": "unknown", "env": "unknown"}
        if TRUTH_PATH.exists():
            try:
                truth = json.loads(TRUTH_PATH.read_text())
                node_info = truth.get("node", node_info)
            except Exception:
                pass

        # Add repo path to node info
        node_info["repo_path"] = str(ROOT)

        return {
            "node": node_info,
            "services": manager.get_all_status(),
            "redis": check_redis(),
            "truth": check_truth(),
            "timestamp": datetime.now().isoformat(),
        }

    @app.get("/api/services/{name}")
    def api_service_status(name: str):
        """Get status of a single service."""
        manager = ServiceManager()
        status = manager.get_status(name)
        if "error" in status:
            raise HTTPException(status_code=404, detail=status["error"])
        return status

    @app.post("/api/services/{name}/start")
    def api_start(name: str, body: Optional[dict] = Body(default=None)):
        """Start a service with optional env overrides."""
        manager = ServiceManager()
        extra_env = {}
        if body and "env" in body:
            extra_env = {k: str(v) for k, v in body["env"].items()}
        result = manager.start(name, extra_env=extra_env)
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to start"))
        return result

    @app.post("/api/services/{name}/stop")
    def api_stop(name: str):
        """Stop a service."""
        manager = ServiceManager()
        result = manager.stop(name)
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to stop"))
        return result

    @app.post("/api/services/{name}/restart")
    def api_restart(name: str):
        """Restart a service."""
        manager = ServiceManager()
        result = manager.restart(name)
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to restart"))
        return result

    @app.get("/api/services/{name}/logs")
    def api_logs(name: str, lines: int = 100):
        """Get recent logs for a service."""
        manager = ServiceManager()
        result = manager.logs(name, lines)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.get("/api/services/{name}/config")
    def api_service_config(name: str):
        """Get service configuration including env vars from truth.json."""
        if not TRUTH_PATH.exists():
            raise HTTPException(status_code=404, detail="truth.json not found")

        truth = json.loads(TRUTH_PATH.read_text())
        components = truth.get("components", {})

        if name not in components:
            raise HTTPException(status_code=404, detail=f"Service '{name}' not found in truth.json")

        comp = components[name]
        env_vars = comp.get("env", {})

        # Categorize env vars for better UI organization
        categorized = {"boolean": [], "number": [], "string": []}

        for key, value in sorted(env_vars.items()):
            val_str = str(value)
            val_lower = val_str.lower()

            if val_lower in ("true", "false"):
                categorized["boolean"].append({"key": key, "default": value, "type": "boolean"})
            elif val_str.replace(".", "").replace("-", "").isdigit():
                categorized["number"].append({"key": key, "default": value, "type": "number"})
            else:
                categorized["string"].append({"key": key, "default": value, "type": "string"})

        return {
            "name": name,
            "meta": comp.get("meta", {}),
            "env": env_vars,
            "categorized": categorized,
        }

    @app.get("/api/redis")
    def api_redis():
        """Get Redis bus status."""
        return check_redis()

    @app.get("/api/redis/status")
    def api_redis_status():
        """Get detailed Redis bus status using ms-busses.sh."""
        script_path = ROOT / "scripts" / "ms-busses.sh"
        if not script_path.exists():
            return check_redis()  # Fallback to simple check

        try:
            result = subprocess.run(
                [str(script_path), "status"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(ROOT)
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "buses": check_redis()
            }
        except Exception as e:
            return {"success": False, "error": str(e), "buses": check_redis()}

    @app.post("/api/redis/start")
    def api_redis_start_all():
        """Start all Redis buses using ms-busses.sh."""
        script_path = ROOT / "scripts" / "ms-busses.sh"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="ms-busses.sh not found")

        try:
            result = subprocess.run(
                [str(script_path), "up"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT)
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "buses": check_redis()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout starting Redis buses"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/redis/stop")
    def api_redis_stop_all():
        """Stop all Redis buses using ms-busses.sh."""
        script_path = ROOT / "scripts" / "ms-busses.sh"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="ms-busses.sh not found")

        try:
            result = subprocess.run(
                [str(script_path), "down"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(ROOT)
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "buses": check_redis()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout stopping Redis buses"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/truth/update")
    def api_truth_update():
        """Run full truth update: build → clear → load."""
        script_path = ROOT / "scripts" / "ms-update-truth.sh"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="ms-update-truth.sh not found")

        try:
            result = subprocess.run(
                [str(script_path), "update", "-y"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT / "scripts")
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Truth update timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/truth/build")
    def api_truth_build():
        """Build truth.json from component JSONs."""
        script_path = ROOT / "scripts" / "ms-update-truth.sh"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="ms-update-truth.sh not found")

        try:
            result = subprocess.run(
                [str(script_path), "build"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(ROOT / "scripts")
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/truth/load")
    def api_truth_load():
        """Load truth.json into system-redis."""
        script_path = ROOT / "scripts" / "ms-update-truth.sh"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="ms-update-truth.sh not found")

        try:
            result = subprocess.run(
                [str(script_path), "load"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(ROOT / "scripts")
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/truth/status")
    def api_truth_status():
        """Get truth status: file exists, loaded in redis, summary."""
        truth_file = ROOT / "scripts" / "truth.json"
        result = {
            "file_exists": truth_file.exists(),
            "loaded_in_redis": check_truth(),
            "summary": None
        }

        if truth_file.exists():
            try:
                truth = json.loads(truth_file.read_text())
                result["summary"] = {
                    "version": truth.get("version"),
                    "description": truth.get("description"),
                    "buses": list(truth.get("buses", {}).keys()),
                    "components": list(truth.get("components", {}).keys())
                }
            except Exception:
                pass

        return result

    @app.post("/api/services/start-all")
    def api_start_all(body: Optional[dict] = Body(default=None)):
        """Start all services with optional env overrides."""
        manager = ServiceManager()
        global_env = {}
        service_env = {}
        if body:
            global_env = {k: str(v) for k, v in body.get("env", {}).items()}
            service_env = body.get("service_env", {})
        return {"results": manager.start_all(extra_env=global_env, service_env=service_env)}

    @app.post("/api/services/stop-all")
    def api_stop_all():
        """Stop all services."""
        manager = ServiceManager()
        return {"results": manager.stop_all()}

    @app.get("/api/reload-truth")
    def api_reload_truth():
        """Reload services from truth.json."""
        global SERVICES
        SERVICES = load_services_from_truth()
        return {"success": True, "services": list(SERVICES.keys())}

    # =========================================================
    # DEPLOYMENT ENDPOINTS
    # =========================================================

    @app.get("/api/deploy/status")
    def api_deploy_status():
        """Get current git status and deployment info."""
        import subprocess

        result = {
            "repo_path": str(ROOT),
            "current_branch": None,
            "current_commit": None,
            "has_changes": False,
            "behind_remote": False,
            "last_pull": None,
        }

        try:
            # Get current branch
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=ROOT, capture_output=True, text=True
            )
            result["current_branch"] = branch.stdout.strip() if branch.returncode == 0 else None

            # Get current commit
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT, capture_output=True, text=True
            )
            result["current_commit"] = commit.stdout.strip() if commit.returncode == 0 else None

            # Check for local changes
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT, capture_output=True, text=True
            )
            result["has_changes"] = bool(status.stdout.strip()) if status.returncode == 0 else False

            # Fetch and check if behind
            subprocess.run(["git", "fetch", "--quiet"], cwd=ROOT, capture_output=True)
            behind = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                cwd=ROOT, capture_output=True, text=True
            )
            if behind.returncode == 0:
                count = int(behind.stdout.strip() or "0")
                result["behind_remote"] = count > 0
                result["commits_behind"] = count

        except Exception as e:
            result["error"] = str(e)

        return result

    @app.post("/api/deploy/pull")
    def api_deploy_pull():
        """Pull latest code from origin/main."""
        import subprocess

        try:
            # Get commit before pull
            before = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT, capture_output=True, text=True
            )
            before_commit = before.stdout.strip() if before.returncode == 0 else "unknown"

            # Pull
            pull = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=ROOT, capture_output=True, text=True
            )

            if pull.returncode != 0:
                return {
                    "success": False,
                    "error": pull.stderr or "Git pull failed",
                    "output": pull.stdout,
                }

            # Get commit after pull
            after = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT, capture_output=True, text=True
            )
            after_commit = after.stdout.strip() if after.returncode == 0 else "unknown"

            # Get changelog if commits changed
            changelog = []
            if before_commit != after_commit:
                log = subprocess.run(
                    ["git", "log", "--oneline", f"{before_commit}..{after_commit}"],
                    cwd=ROOT, capture_output=True, text=True
                )
                if log.returncode == 0:
                    changelog = [line for line in log.stdout.strip().split("\n") if line]

            return {
                "success": True,
                "before_commit": before_commit,
                "after_commit": after_commit,
                "updated": before_commit != after_commit,
                "changelog": changelog,
                "output": pull.stdout,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/deploy/restart-all")
    def api_deploy_restart_all():
        """Restart all services (used after deploy)."""
        manager = ServiceManager()

        # Stop all
        stop_results = manager.stop_all()

        # Brief pause
        import time
        time.sleep(2)

        # Start all
        start_results = manager.start_all()

        return {
            "success": True,
            "stopped": stop_results,
            "started": start_results,
        }

    # SSH options for reliable MiniThree connections
    SSH_OPTS = ["-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]

    def _sync_nginx(nginx_host: str = "MiniThree") -> dict:
        """Copy Nginx config to remote host, test, and reload."""
        import subprocess

        nginx_conf = ROOT / "deploy" / "marketswarm-https.conf"
        if not nginx_conf.exists():
            return {"success": False, "error": "Nginx config not found"}

        try:
            # SCP config to remote host
            scp = subprocess.run(
                ["scp"] + SSH_OPTS + [str(nginx_conf), f"{nginx_host}:/tmp/marketswarm-https.conf"],
                capture_output=True, text=True, timeout=30
            )
            if scp.returncode != 0:
                return {"success": False, "error": f"SCP failed: {scp.stderr}"}

            # SSH: copy to sites-available, test config, reload
            ssh = subprocess.run(
                ["ssh"] + SSH_OPTS + [nginx_host,
                 "sudo cp /tmp/marketswarm-https.conf /etc/nginx/sites-available/marketswarm.conf && "
                 "sudo nginx -t && sudo systemctl reload nginx"],
                capture_output=True, text=True, timeout=30
            )
            return {
                "success": ssh.returncode == 0,
                "output": ssh.stdout,
                "error": ssh.stderr if ssh.returncode != 0 else None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "SSH/SCP timed out (30s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _check_service_health() -> dict:
        """Hit health/status endpoints on each service to verify they're responding."""
        import requests

        health_endpoints = {
            "sse_gateway": "http://127.0.0.1:3001/api/health",
            "journal": "http://127.0.0.1:3002/api/health",
            "vexy_ai": "http://127.0.0.1:3005/api/vexy/health",
            "vexy_proxy": "http://127.0.0.1:3006/health",
            "copilot": "http://127.0.0.1:8095/health",
        }

        results = {}
        for name, url in health_endpoints.items():
            try:
                resp = requests.get(url, timeout=5)
                results[name] = {
                    "healthy": resp.ok,
                    "status_code": resp.status_code,
                    "url": url,
                }
            except requests.exceptions.ConnectionError:
                results[name] = {"healthy": False, "error": "Connection refused", "url": url}
            except requests.exceptions.Timeout:
                results[name] = {"healthy": False, "error": "Timeout", "url": url}
            except Exception as e:
                results[name] = {"healthy": False, "error": str(e), "url": url}

        results["all_healthy"] = all(r.get("healthy", False) for r in results.values())
        return results

    @app.get("/api/deploy/health")
    def api_deploy_health():
        """Check health of all production services."""
        return _check_service_health()

    @app.post("/api/deploy/nginx")
    def api_deploy_nginx(body: dict = None):
        """Sync Nginx config to production (MiniThree)."""
        options = body or {}
        nginx_host = options.get("nginx_host", "MiniThree")
        return _sync_nginx(nginx_host)

    @app.post("/api/deploy/full")
    def api_deploy_full(body: dict = None):
        """
        Full deployment: pull code, restart services, sync nginx, health check.

        Options in body:
        - restart_services: bool (default True)
        - sync_nginx: bool (default True)
        - health_check: bool (default True)
        - nginx_host: str (default "MiniThree")
        """
        import subprocess
        import time

        options = body or {}
        restart_services = options.get("restart_services", True)
        sync_nginx = options.get("sync_nginx", True)
        health_check = options.get("health_check", True)
        nginx_host = options.get("nginx_host", "MiniThree")

        steps = []
        results = {
            "pull": None,
            "restart": None,
            "nginx": None,
            "health": None,
            "success": True,
            "steps": steps,
        }

        # Step 1: Pull
        steps.append({"step": "pull", "status": "running"})
        pull_result = api_deploy_pull()
        results["pull"] = pull_result
        if not pull_result.get("success"):
            steps[-1]["status"] = "failed"
            results["success"] = False
            return results
        steps[-1]["status"] = "done"

        # Step 2: Restart services
        if restart_services:
            steps.append({"step": "restart", "status": "running"})
            manager = ServiceManager()
            stop_results = manager.stop_all()
            time.sleep(2)
            start_results = manager.start_all()
            results["restart"] = {
                "stopped": stop_results,
                "started": start_results,
            }
            steps[-1]["status"] = "done"

        # Step 3: Sync Nginx
        if sync_nginx:
            steps.append({"step": "nginx", "status": "running"})
            nginx_result = _sync_nginx(nginx_host)
            results["nginx"] = nginx_result
            if not nginx_result.get("success"):
                steps[-1]["status"] = "failed"
                # Nginx failure is non-fatal — services are already running
            else:
                steps[-1]["status"] = "done"

        # Step 4: Health check (wait a moment for services to finish starting)
        if health_check:
            steps.append({"step": "health", "status": "running"})
            time.sleep(5)
            health_result = _check_service_health()
            results["health"] = health_result
            steps[-1]["status"] = "done" if health_result.get("all_healthy") else "warning"

        return results

    @app.post("/api/deploy/volume-profile")
    def api_deploy_volume_profile(body: dict = None):
        """
        Receive a volume profile payload and write it to local system-redis.
        Called by the dev SSE Gateway to push VP data to production.
        """
        import json
        import redis
        from datetime import datetime, timezone

        if not body or "vp_data" not in body:
            return {"success": False, "error": "Missing vp_data in request body"}

        vp_data = body["vp_data"]

        # Validate required fields
        for field in ("bin_size", "min_price", "max_price"):
            if field not in vp_data:
                return {"success": False, "error": f"Missing required field: {field}"}

        try:
            r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
            vp_json = json.dumps(vp_data)
            r.set("massive:volume_profile", vp_json)

            # Clear precomputed artifact so /artifact reads fresh VP data
            r.delete("dealer_gravity:artifact:spx")
            r.delete("dealer_gravity:context:spx")

            # Publish update event on both system-redis and market-redis
            # so SSE clients (subscribed on market-redis) get notified
            event = json.dumps({
                "type": "volume_profile_deployed",
                "source": "vp_editor",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            })
            r.publish("dealer_gravity_updated", event)
            try:
                mr = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)
                mr.publish("dealer_gravity_updated", event)
                mr.close()
            except Exception:
                pass  # market-redis notification is best-effort

            return {
                "success": True,
                "message": "Volume profile deployed to production Redis",
                "deployed_at": datetime.now(timezone.utc).isoformat(),
                "data_size": len(vp_json),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/deploy/changelog")
    def api_deploy_changelog(count: int = 20):
        """Get recent git commits."""
        import subprocess

        try:
            log = subprocess.run(
                ["git", "log", f"-{count}", "--oneline", "--decorate"],
                cwd=ROOT, capture_output=True, text=True
            )
            if log.returncode == 0:
                commits = []
                for line in log.stdout.strip().split("\n"):
                    if line:
                        parts = line.split(" ", 1)
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1] if len(parts) > 1 else "",
                        })
                return {"success": True, "commits": commits}
            else:
                return {"success": False, "error": log.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/analytics")
    def api_analytics():
        """Get analytics from all instrumented services."""
        import redis
        import requests

        analytics = {}

        # Redis-based analytics (massive workers)
        redis_analytics_keys = [
            ("massive:spot", "massive:spot:analytics", "market-redis"),
            ("massive:ws", "massive:ws:analytics", "market-redis"),
            ("massive:chain", "massive:chain:analytics", "market-redis"),
            ("massive:model", "massive:model:analytics", "market-redis"),
            ("massive:ws:hydrate", "massive:ws:hydrate:analytics", "market-redis"),
            ("massive:volume_profile", "massive:volume_profile:analytics", "market-redis"),
            ("copilot:alerts", "copilot:alerts:analytics", "intel-redis"),
        ]

        redis_ports = {
            "system-redis": 6379,
            "market-redis": 6380,
            "intel-redis": 6381,
            "echo-redis": 6382,
        }

        for name, key, bus in redis_analytics_keys:
            try:
                port = redis_ports.get(bus, 6379)
                r = redis.Redis(host="127.0.0.1", port=port, decode_responses=True)
                data = r.hgetall(key)
                if data:
                    analytics[name] = {"source": "redis", "bus": bus, "key": key, "data": data}
            except Exception as e:
                analytics[name] = {"source": "redis", "error": str(e)}

        # HTTP-based analytics
        http_endpoints = [
            ("copilot", "http://127.0.0.1:8095/analytics"),
            ("journal", "http://127.0.0.1:3002/api/analytics"),
        ]

        for name, url in http_endpoints:
            try:
                resp = requests.get(url, timeout=2)
                if resp.ok:
                    analytics[name] = {"source": "http", "url": url, "data": resp.json()}
                else:
                    analytics[name] = {"source": "http", "url": url, "error": f"HTTP {resp.status_code}"}
            except requests.exceptions.ConnectionError:
                analytics[name] = {"source": "http", "url": url, "error": "Service not running"}
            except Exception as e:
                analytics[name] = {"source": "http", "url": url, "error": str(e)}

        return {"analytics": analytics, "timestamp": datetime.now().isoformat()}

    @app.get("/api/diagnostics")
    def api_diagnostics():
        """Get data availability diagnostics for market data pipeline."""
        import redis

        symbols = ["SPX", "NDX"]
        results = {
            "ts": int(time.time() * 1000),
            "redis": {"connected": False},
            "data": {},
        }

        # Check market-redis connection
        try:
            r = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)
            r.ping()
            results["redis"]["connected"] = True
        except Exception as e:
            results["redis"]["error"] = str(e)
            return results

        # Check data availability for each symbol
        for symbol in symbols:
            symbol_data = {
                "spot": {"exists": False},
                "heatmap": {"exists": False},
                "gex": {"exists": False},
                "trade_selector": {"exists": False},
            }

            # Check spot
            try:
                spot_raw = r.get(f"massive:model:spot:{symbol}")
                if spot_raw:
                    spot = json.loads(spot_raw)
                    symbol_data["spot"] = {
                        "exists": True,
                        "ts": spot.get("ts"),
                        "value": spot.get("value"),
                        "age_sec": int((time.time() * 1000 - spot.get("ts", 0)) / 1000) if spot.get("ts") else None,
                    }
            except Exception as e:
                symbol_data["spot"]["error"] = str(e)

            # Check heatmap
            try:
                heatmap_raw = r.get(f"massive:heatmap:model:{symbol}:latest")
                if heatmap_raw:
                    heatmap = json.loads(heatmap_raw)
                    symbol_data["heatmap"] = {
                        "exists": True,
                        "ts": heatmap.get("ts"),
                        "tileCount": len(heatmap.get("tiles", {})) if heatmap.get("tiles") else 0,
                        "age_sec": int((time.time() * 1000 - heatmap.get("ts", 0)) / 1000) if heatmap.get("ts") else None,
                    }
            except Exception as e:
                symbol_data["heatmap"]["error"] = str(e)

            # Check GEX
            try:
                gex_raw = r.get(f"massive:gex:model:{symbol}:latest")
                if gex_raw:
                    gex = json.loads(gex_raw)
                    symbol_data["gex"] = {
                        "exists": True,
                        "ts": gex.get("ts"),
                        "age_sec": int((time.time() * 1000 - gex.get("ts", 0)) / 1000) if gex.get("ts") else None,
                    }
            except Exception as e:
                symbol_data["gex"]["error"] = str(e)

            # Check trade_selector
            try:
                selector_raw = r.get(f"massive:selector:model:{symbol}:latest")
                if selector_raw:
                    selector = json.loads(selector_raw)
                    symbol_data["trade_selector"] = {
                        "exists": True,
                        "ts": selector.get("ts"),
                        "vix_regime": selector.get("vix_regime"),
                        "recommendationCount": len(selector.get("recommendations", {})) if selector.get("recommendations") else 0,
                        "error": selector.get("error"),  # Include any error from the model itself
                        "age_sec": int((time.time() - selector.get("ts", 0))) if selector.get("ts") else None,
                    }
            except Exception as e:
                symbol_data["trade_selector"]["error"] = str(e)

            results["data"][symbol] = symbol_data

        # Check global data
        results["data"]["global"] = {}

        # VIX from vexy_ai
        try:
            vix_raw = r.get("vexy_ai:signals:latest")
            if vix_raw:
                vix = json.loads(vix_raw)
                results["data"]["global"]["vix"] = {
                    "exists": True,
                    "value": vix.get("vix"),
                    "ts": vix.get("ts"),
                    "age_sec": int((time.time() * 1000 - vix.get("ts", 0)) / 1000) if vix.get("ts") else None,
                }
            else:
                results["data"]["global"]["vix"] = {"exists": False}
        except Exception as e:
            results["data"]["global"]["vix"] = {"exists": False, "error": str(e)}

        # Market mode
        try:
            mode_raw = r.get("massive:market_mode:latest")
            if mode_raw:
                mode = json.loads(mode_raw)
                results["data"]["global"]["market_mode"] = {
                    "exists": True,
                    "mode": mode.get("mode"),
                    "ts": mode.get("ts"),
                }
            else:
                results["data"]["global"]["market_mode"] = {"exists": False}
        except Exception as e:
            results["data"]["global"]["market_mode"] = {"exists": False, "error": str(e)}

        return results

    @app.get("/api/diagnostics/redis")
    def api_diagnostics_redis(pattern: str = "*", limit: int = 100):
        """Query Redis keys by pattern."""
        import redis

        limit = min(limit, 500)

        try:
            r = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)
            all_keys = r.keys(pattern)
            keys = all_keys[:limit]

            results = []
            for key in keys:
                try:
                    key_type = r.type(key)
                    info = {"key": key, "type": key_type}

                    if key_type == "string":
                        val = r.get(key)
                        info["size"] = len(val) if val else 0
                        try:
                            parsed = json.loads(val)
                            if isinstance(parsed, dict) and "ts" in parsed:
                                info["ts"] = parsed["ts"]
                                # Handle both ms and seconds timestamps
                                ts = parsed["ts"]
                                if ts > 1e12:  # milliseconds
                                    info["age_sec"] = int((time.time() * 1000 - ts) / 1000)
                                else:  # seconds
                                    info["age_sec"] = int(time.time() - ts)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif key_type == "list":
                        info["size"] = r.llen(key)
                    elif key_type == "set":
                        info["size"] = r.scard(key)
                    elif key_type == "hash":
                        info["size"] = r.hlen(key)
                    elif key_type == "zset":
                        info["size"] = r.zcard(key)

                    ttl = r.ttl(key)
                    if ttl > 0:
                        info["ttl"] = ttl

                    results.append(info)
                except Exception as e:
                    results.append({"key": key, "error": str(e)})

            return {
                "pattern": pattern,
                "total": len(all_keys),
                "returned": len(results),
                "keys": results,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/diagnostics/redis/{key:path}")
    def api_diagnostics_redis_key(key: str):
        """Get full value of a specific Redis key."""
        import redis

        try:
            r = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)
            key_type = r.type(key)

            if key_type == "none":
                return {"error": "Key not found", "key": key}

            value = None
            if key_type == "string":
                raw = r.get(key)
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    value = raw
            elif key_type == "list":
                value = r.lrange(key, 0, 100)
            elif key_type == "set":
                value = list(r.smembers(key))
            elif key_type == "hash":
                value = r.hgetall(key)
            elif key_type == "zset":
                value = r.zrange(key, 0, 100, withscores=True)

            ttl = r.ttl(key)

            return {
                "key": key,
                "type": key_type,
                "ttl": ttl if ttl > 0 else None,
                "value": value,
            }
        except Exception as e:
            return {"error": str(e)}

    # ================================================================
    # ML Lab API Proxy (forwards to Journal service)
    # ================================================================

    JOURNAL_API_URL = "http://localhost:3002"

    def proxy_ml_request(path: str, method: str = "GET", body: dict = None):
        """Proxy request to Journal service ML endpoints."""
        import requests
        try:
            url = f"{JOURNAL_API_URL}/api/internal/ml{path}"
            if method == "GET":
                resp = requests.get(url, timeout=5)
            else:
                resp = requests.post(url, json=body, timeout=5)
            return resp.json() if resp.ok else {"error": f"Journal service returned {resp.status_code}"}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to Journal service"}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/ml/circuit-breakers")
    def api_ml_circuit_breakers():
        return proxy_ml_request("/circuit-breakers")

    @app.post("/api/ml/circuit-breakers/check")
    def api_ml_circuit_breakers_check():
        return proxy_ml_request("/circuit-breakers/check", "POST")

    @app.post("/api/ml/circuit-breakers/disable-ml")
    def api_ml_disable():
        return proxy_ml_request("/circuit-breakers/disable-ml", "POST")

    @app.post("/api/ml/circuit-breakers/enable-ml")
    def api_ml_enable():
        return proxy_ml_request("/circuit-breakers/enable-ml", "POST")

    @app.get("/api/ml/models")
    def api_ml_models():
        return proxy_ml_request("/models")

    @app.get("/api/ml/models/champion")
    def api_ml_models_champion():
        return proxy_ml_request("/models/champion")

    @app.get("/api/ml/experiments")
    def api_ml_experiments():
        return proxy_ml_request("/experiments")

    @app.get("/api/ml/decisions")
    def api_ml_decisions(limit: int = 100):
        return proxy_ml_request(f"/decisions?limit={limit}")

    @app.get("/api/ml/daily-performance")
    def api_ml_daily_performance(limit: int = 30):
        return proxy_ml_request(f"/daily-performance?limit={limit}")

    @app.get("/api/ml/equity-curve")
    def api_ml_equity_curve(days: int = 30):
        return proxy_ml_request(f"/equity-curve?days={days}")

    # ================================================================
    # Health Monitoring API
    # ================================================================

    _health_collector.start()

    @app.get("/api/health")
    def api_health():
        """Get unified health status with score."""
        latest = _health_collector.get_latest()
        if not latest:
            return {"status": "initializing", "message": "Health collector starting up"}
        return {
            "score": latest.get("score", 0.0),
            "score_label": _score_label(latest.get("score", 0.0)),
            "ts": latest.get("ts"),
            "ts_iso": latest.get("ts_iso"),
            "redis": latest.get("redis", {}),
            "heartbeats": latest.get("heartbeats", {}),
            "http_health": latest.get("http_health", {}),
            "events_count": len(_health_collector.get_events()),
        }

    @app.get("/api/health/redis")
    def api_health_redis():
        """Get detailed Redis health from last collection."""
        latest = _health_collector.get_latest()
        return {
            "redis": latest.get("redis", {}),
            "ts": latest.get("ts"),
        }

    @app.get("/api/health/heartbeats")
    def api_health_heartbeats():
        """Get heartbeat status for all monitored services."""
        latest = _health_collector.get_latest()
        return {
            "heartbeats": latest.get("heartbeats", {}),
            "ts": latest.get("ts"),
        }

    @app.get("/api/health/history")
    def api_health_history(count: int = 240):
        """Get health score history for timeline chart."""
        count = min(count, 240)
        history = _health_collector.get_history(count)
        return {
            "history": [{"ts": h["ts"], "score": h["score"]} for h in history],
            "total_snapshots": len(history),
        }

    @app.get("/api/health/alerts")
    def api_health_alerts(count: int = 100):
        """Get health alert log (backwards-compatible, returns events)."""
        count = min(count, 100)
        return {
            "alerts": _health_collector.get_alerts(count),
        }

    @app.get("/api/health/events")
    def api_health_events(count: int = 100, severity: str = None):
        """Get health events with optional severity filter."""
        count = min(count, 100)
        return {
            "events": _health_collector.get_events(count, severity),
        }

    @app.post("/api/health/webhook")
    def api_health_webhook(body: dict = Body(default={})):
        """Configure health notification webhook."""
        url = body.get("url", "")
        timeout = int(body.get("timeout", 4))
        _health_collector.configure_webhook(url, timeout)
        return {"success": True, "webhook_url": url, "timeout": timeout}

    @app.get("/api/health/webhook")
    def api_health_webhook_config():
        """Get current webhook configuration."""
        return _health_collector.get_webhook_config()

    # AutoHealer endpoints
    @app.get("/api/health/healer")
    def api_healer_status():
        """Get auto-healer status: enabled, active service, cooldowns, history."""
        return _auto_healer.get_status()

    @app.post("/api/health/healer/toggle")
    def api_healer_toggle(body: dict = Body(default={})):
        """Enable or disable auto-healing."""
        enabled = body.get("enabled", not _auto_healer.enabled)
        _auto_healer.enabled = bool(enabled)
        return {"success": True, "enabled": _auto_healer.enabled}

    @app.get("/api/health/healer/log")
    def api_healer_log(lines: int = 100):
        """Get recent healer log entries."""
        return {"log": _auto_healer.get_log(lines)}

    # ── Tier Gates ───────────────────────────────────────────
    def _default_tier_gates() -> dict:
        """Return the default tier gates configuration."""
        defaults = {
            "vexy_chat_rate":            {"type": "number",  "label": "Vexy Chat (per hour)",       "value": -1},
            "vexy_interaction_rate":     {"type": "number",  "label": "Vexy Interaction (per hour)", "value": -1},
            "risk_graph_max_strategies": {"type": "number",  "label": "Risk Graph Max Strategies",   "value": -1},
            "trade_log_max_active":      {"type": "number",  "label": "Trade Log Max Active",        "value": -1},
            "position_max_concurrent":   {"type": "number",  "label": "Position Max Concurrent",     "value": -1},
            "alert_max_active":          {"type": "number",  "label": "Alert Max Active",            "value": -1},
            "journal_access":            {"type": "boolean", "label": "Journal Access",              "value": True},
            "playbook_access":           {"type": "boolean", "label": "Playbook Access",             "value": True},
            "edge_lab_access":           {"type": "boolean", "label": "Edge Lab Access",             "value": True},
            "routine_briefing_access":   {"type": "boolean", "label": "Routine Briefing",            "value": True},
            "heatmap_access":            {"type": "boolean", "label": "Heatmap Access",              "value": True},
            "dg_analysis_access":        {"type": "boolean", "label": "DG Analysis Access",          "value": True},
            "import_access":             {"type": "boolean", "label": "Import Functionality",        "value": True},
            "leaderboard_access":        {"type": "boolean", "label": "Leaderboard Access",          "value": True},
        }
        # Build tier overrides — observer gets restricted defaults, others get unlimited
        observer_overrides = {}
        for key, feat in defaults.items():
            if feat["type"] == "number":
                observer_overrides[key] = 5  # sensible default limit
            else:
                observer_overrides[key] = True  # access allowed by default, admin can toggle off
        # Activator and Navigator get unlimited (-1 / True)
        activator_overrides = {}
        navigator_overrides = {}
        for key, feat in defaults.items():
            activator_overrides[key] = -1 if feat["type"] == "number" else True
            navigator_overrides[key] = -1 if feat["type"] == "number" else True

        return {
            "mode": "full_production",
            "updated_at": datetime.now().isoformat(),
            "defaults": defaults,
            "allowed_tiers": {
                "observer": True,
                "activator": True,
                "navigator": True,
                "coaching": True,
            },
            "tiers": {
                "observer": observer_overrides,
                "activator": activator_overrides,
                "navigator": navigator_overrides,
            },
        }

    def _get_redis_tier_gates():
        """Read tier_gates from system-redis. Returns dict or None."""
        import redis as _redis
        try:
            r = _redis.Redis(host="127.0.0.1", port=6379, socket_timeout=2)
            raw = r.get("tier_gates")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _save_redis_tier_gates(config: dict):
        """Write tier_gates to system-redis and publish update notification."""
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, socket_timeout=2)
        config["updated_at"] = datetime.now().isoformat()
        r.set("tier_gates", json.dumps(config))
        r.publish("tier_gates:updated", json.dumps({"updated_at": config["updated_at"]}))

    @app.get("/api/tier-gates")
    def api_get_tier_gates():
        """Get current tier gates configuration from Redis."""
        config = _get_redis_tier_gates()
        if not config:
            # Return defaults (not yet saved to Redis)
            config = _default_tier_gates()
        return config

    @app.post("/api/tier-gates")
    def api_save_tier_gates(body: dict = Body(default={})):
        """Save tier gates configuration to Redis."""
        # Merge incoming body with defaults to ensure schema completeness
        defaults = _default_tier_gates()
        # Accept full config or partial updates
        if "mode" in body:
            defaults["mode"] = body["mode"]
        if "tiers" in body:
            for tier_name, overrides in body["tiers"].items():
                if tier_name in defaults["tiers"]:
                    defaults["tiers"][tier_name].update(overrides)
        if "allowed_tiers" in body:
            for tier_name, allowed in body["allowed_tiers"].items():
                if tier_name in defaults["allowed_tiers"]:
                    defaults["allowed_tiers"][tier_name] = bool(allowed)
        if "defaults" in body:
            for key, feat in body["defaults"].items():
                if key in defaults["defaults"]:
                    defaults["defaults"][key].update(feat)
        try:
            _save_redis_tier_gates(defaults)
            return {"success": True, "config": defaults}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

    @app.post("/api/tier-gates/reset")
    def api_reset_tier_gates():
        """Reset tier gates to defaults (full_production mode, all unlimited)."""
        config = _default_tier_gates()
        try:
            _save_redis_tier_gates(config)
            return {"success": True, "config": config}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to reset: {str(e)}")

    return app


def serve_web_ui(port: int = 8099, host: str = "0.0.0.0"):
    """Start the web UI server."""
    import uvicorn

    # Load node info for display
    node_name = "unknown"
    node_env = "unknown"
    if TRUTH_PATH.exists():
        try:
            truth = json.loads(TRUTH_PATH.read_text())
            node_info = truth.get("node", {})
            node_name = node_info.get("name", "unknown")
            node_env = node_info.get("env", "unknown")
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"  MarketSwarm Node Admin")
    print(f"  Node: {node_name} ({node_env})")
    print(f"  http://localhost:{port}")
    print(f"{'='*60}\n")

    app = create_web_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


# ============================================================
# CLI Interface
# ============================================================

def _format_uptime(seconds: int) -> str:
    """Format uptime seconds to human readable string."""
    if seconds is None:
        return "-"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return f"{seconds}s"


def print_status(statuses: List[dict], redis: dict, truth: bool):
    """Print formatted status."""
    print("\n" + "─" * 60)
    print(" MarketSwarm Service Status")
    print("─" * 60)

    # Redis status
    print("\nRedis Buses:")
    for name, info in redis.items():
        status = "\033[32mRUNNING\033[0m" if info["running"] else "\033[31mSTOPPED\033[0m"
        print(f"  {name:14} :{info['port']}  [{status}]")

    # Truth status
    if truth:
        print("\n\033[32m[OK]\033[0m Truth loaded in system-redis")
    else:
        print("\n\033[33m[WARN]\033[0m Truth NOT loaded in system-redis")

    # Services
    print("\n" + "─" * 60)
    print(f"  {'SERVICE':<14} {'PORT':<6} {'UPTIME':<10} STATUS")
    print(f"  {'-'*14:<14} {'-'*4:<6} {'-'*10:<10} ------")

    for s in statuses:
        port = str(s["port"]) if s["port"] else "-"
        uptime = _format_uptime(s.get("uptime_seconds")) if s["running"] else "-"
        if s["running"]:
            status = f"\033[32mRUNNING\033[0m (PID: {s['pid']})"
        else:
            status = "\033[31mSTOPPED\033[0m"
        print(f"  {s['name']:<14} {port:<6} {uptime:<10} {status}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="MarketSwarm Node Admin - Self-configuring service manager",
        epilog="Repo discovery: --repo > $MARKETSWARM_REPO > ~/.marketswarm/config.json > auto-detect"
    )

    # Global argument for repo path
    parser.add_argument(
        "--repo",
        metavar="PATH",
        help="Path to MarketSwarm repo (overrides env/config)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status
    subparsers.add_parser("status", help="Show status of all services")

    # start
    start_p = subparsers.add_parser("start", help="Start service(s)")
    start_p.add_argument("service", nargs="?", help="Service name (omit for all)")
    start_p.add_argument("-f", "--foreground", action="store_true", help="Run in foreground")

    # stop
    stop_p = subparsers.add_parser("stop", help="Stop service(s)")
    stop_p.add_argument("service", nargs="?", help="Service name (omit for all)")

    # restart
    restart_p = subparsers.add_parser("restart", help="Restart service(s)")
    restart_p.add_argument("service", nargs="?", help="Service name (omit for all)")

    # logs
    logs_p = subparsers.add_parser("logs", help="View service logs")
    logs_p.add_argument("service", help="Service name")
    logs_p.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")
    logs_p.add_argument("-f", "--follow", action="store_true", help="Follow log output")

    # list
    subparsers.add_parser("list", help="List available services")

    # serve (web UI)
    serve_p = subparsers.add_parser("serve", help="Start web UI server")
    serve_p.add_argument("-p", "--port", type=int, default=8099, help="Port (default: 8099)")
    serve_p.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")

    # config - save repo path to config file
    config_p = subparsers.add_parser("config", help="Configure admin settings")
    config_p.add_argument("--set-repo", metavar="PATH", help="Save repo path to config file")
    config_p.add_argument("--show", action="store_true", help="Show current configuration")

    # info - show node information
    subparsers.add_parser("info", help="Show node information")

    args = parser.parse_args()

    # Handle config command before discovering repo
    if args.command == "config":
        if args.set_repo:
            repo_path = Path(args.set_repo).resolve()
            if not _validate_repo(repo_path):
                print(f"\033[33mWarning:\033[0m {repo_path} doesn't look like a MarketSwarm repo")
                print("Saving anyway...")
            config = load_admin_config()
            config["repo"] = str(repo_path)
            save_admin_config(config)
            print(f"\033[32m[OK]\033[0m Saved repo path: {repo_path}")
            print(f"     Config file: {CONFIG_FILE}")
            return

        if args.show:
            config = load_admin_config()
            print("MarketSwarm Admin Configuration")
            print(f"  Config file: {CONFIG_FILE}")
            print(f"  Repo path:   {config.get('repo', '(not set)')}")
            return

        parser.parse_args(["config", "--help"])
        return

    # Discover and configure repo path
    repo_path = discover_repo_path(args.repo)
    configure_paths(repo_path)

    # Reload services from truth.json
    global SERVICES
    SERVICES = load_services_from_truth()

    manager = ServiceManager()

    if args.command == "status" or args.command is None:
        statuses = manager.get_all_status()
        redis = check_redis()
        truth = check_truth()
        print_status(statuses, redis, truth)

    elif args.command == "start":
        if args.service:
            if args.foreground:
                print(f"Starting {args.service} in foreground...")
                result = manager.start(args.service, foreground=True)
                # Won't reach here if foreground
            else:
                result = manager.start(args.service)
                if result.get("success"):
                    print(f"\033[32m[OK]\033[0m {result.get('message', 'Started')}")
                    if result.get("log"):
                        print(f"     Log: {result['log']}")
                else:
                    print(f"\033[31m[ERROR]\033[0m {result.get('error', 'Failed')}")
                    sys.exit(1)
        else:
            print("Starting all services...")
            results = manager.start_all()
            for r in results:
                if r.get("success"):
                    print(f"  \033[32m[OK]\033[0m {r['name']}")
                else:
                    print(f"  \033[31m[FAIL]\033[0m {r['name']}: {r.get('error', 'Unknown error')}")

    elif args.command == "stop":
        if args.service:
            result = manager.stop(args.service)
            if result.get("success"):
                print(f"\033[32m[OK]\033[0m {result.get('message', 'Stopped')}")
            else:
                print(f"\033[31m[ERROR]\033[0m {result.get('error', 'Failed')}")
                sys.exit(1)
        else:
            print("Stopping all services...")
            results = manager.stop_all()
            for r in results:
                if r.get("success"):
                    print(f"  \033[32m[OK]\033[0m {r['name']}: {r.get('message', 'Stopped')}")
                else:
                    print(f"  \033[31m[FAIL]\033[0m {r['name']}: {r.get('error', 'Unknown error')}")

    elif args.command == "restart":
        if args.service:
            result = manager.restart(args.service)
            if result.get("success"):
                print(f"\033[32m[OK]\033[0m {result.get('message', 'Restarted')}")
            else:
                print(f"\033[31m[ERROR]\033[0m {result.get('error', 'Failed')}")
                sys.exit(1)
        else:
            print("Restarting all services...")
            manager.stop_all()
            time.sleep(2)
            results = manager.start_all()
            for r in results:
                if r.get("success"):
                    print(f"  \033[32m[OK]\033[0m {r['name']}")
                else:
                    print(f"  \033[31m[FAIL]\033[0m {r['name']}: {r.get('error', 'Unknown error')}")

    elif args.command == "logs":
        if args.follow:
            # Tail -f equivalent
            log_file = manager._log_file(args.service)
            if not log_file.exists():
                print(f"No log file for {args.service}")
                sys.exit(1)
            try:
                subprocess.run(["tail", "-f", str(log_file)])
            except KeyboardInterrupt:
                pass
        else:
            result = manager.logs(args.service, args.lines)
            if "error" in result:
                print(f"\033[31m[ERROR]\033[0m {result['error']}")
                sys.exit(1)
            print(result.get("logs", ""))

    elif args.command == "list":
        print("\nAvailable services:")
        print(f"  {'NAME':<14} {'PORT':<6} DESCRIPTION")
        print(f"  {'-'*14:<14} {'-'*4:<6} -----------")
        for name, config in SERVICES.items():
            port = str(config.port) if config.port > 0 else "-"
            print(f"  {name:<14} {port:<6} {config.description}")
        print()

    elif args.command == "info":
        # Show node information
        node_info = {"name": "unknown", "env": "unknown"}
        if TRUTH_PATH.exists():
            try:
                truth = json.loads(TRUTH_PATH.read_text())
                node_info = truth.get("node", node_info)
            except Exception:
                pass

        print("\nMarketSwarm Node Information")
        print(f"  Node name:     {node_info.get('name', 'unknown')}")
        print(f"  Environment:   {node_info.get('env', 'unknown')}")
        print(f"  Repo path:     {ROOT}")
        print(f"  Truth file:    {TRUTH_PATH}")
        print(f"  Services:      {len(SERVICES)}")
        print(f"  Config file:   {CONFIG_FILE}")
        print()

        # List core vs optional services
        core_services = {"vexy_ai", "healer", "mesh"}  # TODO: make this configurable
        node_services = set(SERVICES.keys())

        core_present = core_services & node_services
        optional = node_services - core_services

        print("  Core services:")
        for s in sorted(core_present):
            print(f"    - {s}")
        if not core_present:
            print("    (none detected)")

        print("  Optional services:")
        for s in sorted(optional):
            print(f"    - {s}")
        print()

    elif args.command == "serve":
        print(f"Managing node: {ROOT}")
        serve_web_ui(port=args.port, host=args.host)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
