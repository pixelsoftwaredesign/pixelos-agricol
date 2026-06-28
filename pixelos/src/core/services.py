"""Gestionnaire de services PixelOS.

Centralise le cycle de vie de tous les services :
  - Docker    : MySQL, MongoDB, Mosquitto
  - Backend   : Spring Boot Java (:8080)
  - Dashboard : Streamlit (:8501)
  - PixelOS   : Web UI (:9999)

Usage:
    from core.services import ServiceManager
    svc = ServiceManager()
    svc.status()
    svc.start("backend")
    svc.stop("mongodb")
"""

import os
import sys
import json
import time
import signal
import structlog
import subprocess
from pathlib import Path
from datetime import datetime

log = structlog.get_logger()

ROOT = Path(__file__).resolve().parent.parent.parent  # pixelos/
PROJECT_ROOT = ROOT.parent  # agricol/
DOCKER_DIR = PROJECT_ROOT / "docker"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
BACKEND_DIR = PROJECT_ROOT / "backend"


SERVICES = {
    "mysql": {
        "name": "MySQL",
        "type": "docker",
        "container": "agricol-mysql",
        "port": 3306,
        "compose_service": "mysql",
    },
    "mongodb": {
        "name": "MongoDB",
        "type": "docker",
        "container": "agricol-mongodb",
        "port": 27017,
        "compose_service": "mongodb",
    },
    "mosquitto": {
        "name": "Mosquitto MQTT",
        "type": "docker",
        "container": "agricol-mosquitto",
        "port": 1883,
        "compose_service": "mosquitto",
    },
    "backend": {
        "name": "Backend API",
        "type": "java",
        "port": 8080,
        "workdir": str(BACKEND_DIR),
        "cmd": ["mvn", "spring-boot:run"],
        "logfile": str(ROOT / "logs" / "backend.log"),
        "ready_pattern": "Started AgricolApplication",
    },
    "dashboard": {
        "name": "Dashboard Streamlit",
        "type": "python",
        "port": 8501,
        "workdir": str(PROJECT_ROOT),
        "cmd": [sys.executable, "-m", "streamlit", "run",
                str(DASHBOARD_DIR / "app.py"),
                "--server.port", "8501",
                "--server.headless", "true"],
        "logfile": str(ROOT / "logs" / "dashboard.log"),
        "ready_pattern": "Network URL:",
    },
    "pixelos-web": {
        "name": "PixelOS Web",
        "type": "python",
        "port": 9999,
        "workdir": str(ROOT),
        "cmd": [sys.executable, "-m", "web.app"],
        "logfile": str(ROOT / "logs" / "pixelos-web.log"),
        "ready_pattern": "PixelOS Web",
    },
}


class ServiceManager:
    """Manage all PixelOS services."""

    def __init__(self):
        (ROOT / "logs").mkdir(exist_ok=True)

    # ── Docker ──────────────────────────────────────────────

    def _docker_ps(self, container: str) -> dict:
        try:
            r = subprocess.run(
                ["docker", "ps", "--filter", f"name={container}",
                 "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"],
                capture_output=True, timeout=10)
            out = self._decode(r.stdout)
            if r.returncode == 0 and out.strip():
                parts = out.strip().split("|")
                status = parts[1] if len(parts) > 1 else "unknown"
                return {"running": "Up" in status, "status": status, "ports": parts[2] if len(parts) > 2 else ""}
        except Exception:
            pass
        return {"running": False, "status": "stopped", "ports": ""}

    @staticmethod
    def _decode(b: bytes) -> str:
        return b.decode("utf-8", errors="replace") if b else ""

    def _docker_start(self, container: str, compose_service: str) -> bool:
        if compose_service:
            r = subprocess.run(
                ["docker", "compose", "-f", str(DOCKER_DIR / "docker-compose.yml"),
                 "up", "-d", compose_service],
                capture_output=True, timeout=60)
            return r.returncode == 0
        r = subprocess.run(["docker", "start", container], capture_output=True, timeout=30)
        return r.returncode == 0

    def _docker_stop(self, container: str) -> bool:
        r = subprocess.run(["docker", "stop", container], capture_output=True, timeout=30)
        return r.returncode == 0

    def _docker_logs(self, container: str, tail: int = 50) -> str:
        try:
            r = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container],
                capture_output=True, timeout=10)
            return self._decode(r.stdout) or self._decode(r.stderr)
        except Exception as e:
            return f"Error: {e}"

    # ── Process (Java, Python) ──────────────────────────────

    def _find_pid_by_port(self, port: int) -> int:
        """Find PID listening on a given port."""
        try:
            if sys.platform == "win32":
                r = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, timeout=10)
                for line in self._decode(r.stdout).splitlines():
                    if f":{port}" in line and "LISTEN" in line:
                        parts = line.strip().split()
                        return int(parts[-1])
            else:
                r = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True, timeout=10)
                out = self._decode(r.stdout)
                if out.strip():
                    return int(out.strip().splitlines()[0])
        except Exception:
            pass
        return 0

    def _process_running(self, port: int) -> bool:
        return self._find_pid_by_port(port) > 0

    def _kill_by_port(self, port: int):
        pid = self._find_pid_by_port(port)
        if pid:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=10)
                else:
                    os.kill(pid, signal.SIGTERM)
                log.info("Process killed", pid=pid, port=port)
            except Exception as e:
                log.warning("Kill failed", error=str(e))

    def _start_process(self, svc: dict) -> bool:
        """Start a non-Docker service process."""
        port = svc["port"]
        # Kill existing process on port
        self._kill_by_port(port)
        time.sleep(1)

        logfile = svc.get("logfile")
        logf = open(logfile, "a") if logfile else subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc.get("workdir"),
                stdout=logf,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            log.info("Process started", name=svc["name"], pid=proc.pid, port=port)

            # Wait for ready pattern
            ready = svc.get("ready_pattern", "")
            if ready and logfile:
                for _ in range(30):
                    time.sleep(1)
                    if self._process_running(port):
                        try:
                            with open(logfile, "r") as f:
                                if ready in f.read():
                                    return True
                        except Exception:
                            pass
                # Timeout but process is running
                return self._process_running(port)
            return True
        except Exception as e:
            log.error("Start failed", name=svc["name"], error=str(e))
            return False

    # ── API publique ────────────────────────────────────────

    def status(self, service: str = None) -> list:
        """Return status of all or one service."""
        names = [service] if service else SERVICES
        results = []
        for key, svc in SERVICES.items():
            if service and key != service:
                continue
            s = {"id": key, "name": svc["name"], "port": svc["port"], "type": svc["type"]}
            if svc["type"] == "docker":
                info = self._docker_ps(svc["container"])
                s["running"] = info["running"]
                s["status"] = info["status"]
                s["ports"] = info["ports"]
            else:
                running = self._process_running(svc["port"])
                s["running"] = running
                s["status"] = "running" if running else "stopped"
                s["pid"] = self._find_pid_by_port(svc["port"]) if running else None
            results.append(s)
        return results

    def start(self, service: str = None) -> dict:
        """Start one or all services."""
        if service:
            svc = SERVICES.get(service)
            if not svc:
                return {"status": "error", "message": f"Service inconnu: {service}"}
            ok = self._docker_start(svc["container"], svc.get("compose_service", "")) if svc["type"] == "docker" else self._start_process(svc)
            return {"status": "ok" if ok else "error", "service": service}
        results = {}
        for key in SERVICES:
            results[key] = self.start(key)
        return {"status": "ok", "results": results}

    def stop(self, service: str = None) -> dict:
        """Stop one or all services."""
        if service:
            svc = SERVICES.get(service)
            if not svc:
                return {"status": "error", "message": f"Service inconnu: {service}"}
            if svc["type"] == "docker":
                ok = self._docker_stop(svc["container"])
            else:
                self._kill_by_port(svc["port"])
                ok = not self._process_running(svc["port"])
            return {"status": "ok" if ok else "error", "service": service}
        results = {}
        for key in reversed(list(SERVICES.keys())):
            results[key] = self.stop(key)
        return {"status": "ok", "results": results}

    def restart(self, service: str = None) -> dict:
        """Restart one or all services."""
        self.stop(service)
        time.sleep(2)
        return self.start(service)

    def logs(self, service: str, tail: int = 50) -> str:
        """Get logs for a service."""
        svc = SERVICES.get(service)
        if not svc:
            return f"Service inconnu: {service}"
        if svc["type"] == "docker":
            return self._docker_logs(svc["container"], tail)
        logfile = svc.get("logfile")
        if logfile and Path(logfile).exists():
            with open(logfile, "r") as f:
                lines = f.readlines()
            return "".join(lines[-tail:])
        return f"Aucun log pour {service}"

    def health(self) -> dict:
        """Quick health check of all services."""
        st = self.status()
        return {
            "total": len(st),
            "running": sum(1 for s in st if s["running"]),
            "stopped": sum(1 for s in st if not s["running"]),
            "services": st,
            "timestamp": datetime.now().isoformat(),
        }

    # ── Auto-start au boot ──────────────────────────────────

    def autostart_install(self) -> dict:
        """Enregistre pixelos-agent comme service de démarrage OS."""
        platform = sys.platform
        agent_path = str(ROOT / "src" / "agent" / "agent.py")
        log.info("Installation autostart", platform=platform)

        try:
            if platform == "win32":
                return self._autostart_windows(agent_path)
            elif platform in ("linux", "linux2"):
                return self._autostart_systemd(agent_path)
            elif platform == "openbsd" or "openbsd" in platform:
                return self._autostart_openbsd(agent_path)
            else:
                return {"status": "error",
                        "message": f"Plateforme non supportée: {platform}"}
        except Exception as e:
            log.error("Autostart install failed", error=str(e))
            return {"status": "error", "message": str(e)}

    def _autostart_windows(self, agent_path: str) -> dict:
        """Install via Windows Task Scheduler or Run registry key."""
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path,
                                 0, winreg.KEY_SET_VALUE)
            cmd = f'"{sys.executable}" "{agent_path}"'
            winreg.SetValueEx(key, "PixelOSAgent", 0,
                              winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            return {"status": "ok",
                    "platform": "windows",
                    "method": "HKCU\\Run",
                    "cmd": cmd}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _autostart_systemd(self, agent_path: str) -> dict:
        """Create systemd service unit."""
        unit = f"""[Unit]
Description=PixelOS Agent
After=network.target docker.service
Wants=docker.service

[Service]
ExecStart={sys.executable} {agent_path}
Environment=PIXELOS_NODE_ID=pixelos-server
Environment=PIXELOS_ROLE=server
Environment=PYTHONPATH={ROOT / "src"}
WorkingDirectory={ROOT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        unit_path = "/etc/systemd/system/pixelos-agent.service"
        try:
            with open(unit_path, "w") as f:
                f.write(unit)
            subprocess.run(["systemctl", "daemon-reload"], timeout=10)
            subprocess.run(["systemctl", "enable", "pixelos-agent"], timeout=10)
            return {"status": "ok", "platform": "linux",
                    "unit": unit_path}
        except PermissionError:
            return {"status": "error",
                    "message": "Permission refusée: exécuter avec sudo"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _autostart_openbsd(self, agent_path: str) -> dict:
        """Create OpenBSD rc script."""
        rc_content = f"""#!/bin/sh
#
# PixelOS Agent - /etc/rc.d/pixelos_agent
#
daemon="{sys.executable}"
daemon_flags="{agent_path}"
daemon_user="root"

. /etc/rc.d/rc.subr

pexp="${{daemon}}.*${{daemon_flags}}"
rc_reload=NO

rc_cmd $1
"""
        rc_path = "/etc/rc.d/pixelos_agent"
        try:
            with open(rc_path, "w") as f:
                f.write(rc_content)
            os.chmod(rc_path, 0o755)
            subprocess.run(["rcctl", "enable", "pixelos_agent"], timeout=10)
            return {"status": "ok", "platform": "openbsd",
                    "rc_path": rc_path}
        except PermissionError:
            return {"status": "error",
                    "message": "Permission refusée: exécuter avec doas"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def autostart_remove(self) -> dict:
        """Désenregistre l'autostart."""
        platform = sys.platform
        try:
            if platform == "win32":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "PixelOSAgent")
                winreg.CloseKey(key)
                return {"status": "ok", "platform": "windows"}
            elif platform in ("linux", "linux2"):
                subprocess.run(["systemctl", "disable", "pixelos-agent"],
                               timeout=10)
                Path("/etc/systemd/system/pixelos-agent.service").unlink(missing_ok=True)
                return {"status": "ok", "platform": "linux"}
            elif "openbsd" in platform:
                subprocess.run(["rcctl", "disable", "pixelos_agent"], timeout=10)
                Path("/etc/rc.d/pixelos_agent").unlink(missing_ok=True)
                return {"status": "ok", "platform": "openbsd"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def autostart_status(self) -> dict:
        """Vérifie si l'autostart est installé."""
        platform = sys.platform
        try:
            if platform == "win32":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run")
                val, _ = winreg.QueryValueEx(key, "PixelOSAgent")
                winreg.CloseKey(key)
                return {"installed": True, "platform": "windows", "cmd": val}
            elif platform in ("linux", "linux2"):
                r = subprocess.run(
                    ["systemctl", "is-enabled", "pixelos-agent"],
                    capture_output=True, text=True, timeout=10)
                enabled = r.stdout.strip() == "enabled"
                return {"installed": enabled, "platform": "linux",
                        "status": r.stdout.strip()}
            elif "openbsd" in platform:
                r = subprocess.run(
                    ["rcctl", "check", "pixelos_agent"],
                    capture_output=True, text=True, timeout=10)
                return {"installed": r.returncode == 0, "platform": "openbsd"}
            return {"installed": False, "platform": platform}
        except FileNotFoundError:
            return {"installed": False, "platform": platform}
        except Exception as e:
            return {"installed": False, "error": str(e)}

    def summary(self) -> str:
        """Return a human-readable table."""
        st = self.status()
        lines = []
        lines.append("-" * 80)
        lines.append(f"{'Service':<25} {'Port':<8} {'Status':<20} {'Details'}")
        lines.append("-" * 80)
        for s in st:
            icon = "RUN" if s["running"] else "STOP"
            detail = s.get("status", s.get("pid", ""))
            lines.append(f"  {s['name']:<23} {s['port']:<8} [{icon}] {detail}")
        lines.append("-" * 80)
        lines.append(f"  {sum(1 for s in st if s['running'])}/{len(st)} services en marche")
        return "\n".join(lines)
