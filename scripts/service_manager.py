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
ADMIN_VERSION = "1.1.0"
ADMIN_BUILD_DATE = "2026-02-03"
ADMIN_FEATURES = [
    {"id": "service-mgmt", "name": "Service Management", "desc": "Start, stop, restart services"},
    {"id": "log-viewer", "name": "Log Viewer", "desc": "View and tail service logs"},
    {"id": "env-overrides", "name": "ENV Overrides", "desc": "Override truth.json env vars per service"},
    {"id": "analytics", "name": "Analytics Dashboard", "desc": "View service instrumentation data"},
    {"id": "alerts", "name": "System Alerts", "desc": "Auto-detect and display errors from services and analytics"},
    {"id": "self-config", "name": "Self-Configuring", "desc": "Auto-discover node from repo path"},
    {"id": "live-status", "name": "Live Status", "desc": "Auto-refresh service status every 5s"},
    {"id": "uptime-tracking", "name": "Uptime Tracking", "desc": "Track service uptime when started via admin"},
]

import os
import sys
import json
import time
import signal
import subprocess
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime

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
        is_python = name != "sse"

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

            # Publish update event so SSE clients refresh
            event = json.dumps({
                "type": "volume_profile_deployed",
                "source": "vp_editor",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            })
            r.publish("dealer_gravity_updated", event)

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
