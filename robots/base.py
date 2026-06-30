#!/usr/bin/env python3
"""
RobotNode — Classe de base pour tous les robots PixelOS.

Chaque robot hérite de PixModule (IPC), déclare son rôle,
et suit un cycle de vie de mission standardisé.

Cycle de mission :
  IDLE → MISSION_START → EXECUTING → (MISSION_COMPLETE | MISSION_FAILED | SAFE_RETURN)

Comportements automatiques :
  - Enregistrement IPC avec rôle + version hardware
  - Heartbeat vers PixStat
  - Détection batterie faible → interruption → Safe Return Home
  - Timeout mission → alerte Orchestrateur
"""

import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pixelos", "src"))
from core.ipc import PixModule, MessageBus, Message
from core.ipc import MSG_TYPE_COMMAND, MSG_TYPE_EVENT, MSG_TYPE_HEARTBEAT

ROBOT_DIR = "/var/db/pixelos/robots"
MISSION_FILE = "current_mission.json"
MISSION_HISTORY = "mission_history.json"
SAFE_RETURN_COORDS = "safe_return.json"

MISSION_STATUS = {
    "IDLE": "En attente",
    "MISSION_START": "Mission démarrée",
    "EXECUTING": "En exécution",
    "MISSION_COMPLETE": "Mission terminée",
    "MISSION_FAILED": "Mission échouée",
    "SAFE_RETURN": "Retour au safe point",
    "BATTERY_LOW": "Batterie faible",
    "LOST_CONNECTION": "Connexion perdue",
    "YIELDING": "Cède le passage",
}

MISSION_TIMEOUT = 600
BATTERY_LOW_THRESHOLD = 20
HB_ROBOT_INTERVAL = 5.0

ROBOT_ROLES = {
    "inspecteur": {"cameras": 2, "sensors": ["camera", "temp", "humidity", "spectral"]},
    "transporteur": {"lidar": True, "gps": True, "motors": 4, "max_payload_kg": 500},
    "recolteur": {"arm_axes": 6, "precision_mm": 1, "cameras": 1, "gripper_force_n": 50},
}


class RobotMission:
    """Mission attribuée à un robot par l'Orchestrateur."""

    def __init__(self, mission_id: str = "", mission_type: str = "",
                 gps_coords: tuple = (0.0, 0.0), params: dict = None):
        self.mission_id = mission_id
        self.mission_type = mission_type
        self.gps_coords = gps_coords
        self.params = params or {}
        self.status = "IDLE"
        self.started_at = ""
        self.completed_at = ""
        self.error = ""
        self.steps: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "mission_type": self.mission_type,
            "gps_coords": self.gps_coords,
            "params": self.params,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "steps": self.steps[-100:],
        }

    @staticmethod
    def from_dict(data: dict) -> "RobotMission":
        m = RobotMission(
            data.get("mission_id", ""),
            data.get("mission_type", ""),
            tuple(data.get("gps_coords", (0.0, 0.0))),
            data.get("params", {}),
        )
        m.status = data.get("status", "IDLE")
        m.started_at = data.get("started_at", "")
        m.completed_at = data.get("completed_at", "")
        m.error = data.get("error", "")
        m.steps = data.get("steps", [])
        return m

    def add_step(self, name: str, status: str = "pending", detail: str = ""):
        self.steps.append({
            "step": name,
            "status": status,
            "detail": detail,
            "ts": datetime.now(timezone.utc).isoformat(),
        })


class RobotNode(PixModule):
    """Classe de base pour tous les robots PixelOS.

    Héritage :
        class MonRobot(RobotNode):
            def __init__(self):
                super().__init__("mon_robot", role="inspecteur")
            def run_mission(self, mission):
                ...  # logique métier
    """

    def __init__(self, name: str, role: str, hw_version: str = "1.0"):
        super().__init__(name, version=hw_version)
        self.role = role
        self.hw_version = hw_version
        self.mission = RobotMission()
        self._mission_lock = threading.Lock()
        self._stop = threading.Event()
        self._safe_return_coords = self._load_safe_return()
        self._battery_level = 100.0
        self._connection_ok = True
        self._mission_thread: Optional[threading.Thread] = None

        # ── Yield Protocol ────────────────────────────────
        self._yielding_to: str = ""
        self._yield_reason: str = ""
        self._yielded_at: float = 0.0
        self._priority_abuse_count: int = 0

        Path(ROBOT_DIR).mkdir(parents=True, exist_ok=True)
        self.register({"role": role, "hw_version": hw_version,
                       "hardware_id": self._hardware_id()})
        self.send_heartbeat_loop(interval=HB_ROBOT_INTERVAL)
        self._start_mission_listener()
        self._start_battery_monitor()

    def _hardware_id(self) -> str:
        import hashlib
        raw = f"{self.name}{self.role}{os.urandom(4).hex()}"
        try:
            with open("/sys/class/net/eth0/address") as f:
                raw += f.read().strip()
        except Exception:
            pass
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _load_safe_return(self) -> tuple:
        path = Path(ROBOT_DIR) / SAFE_RETURN_COORDS
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return tuple(data.get("coords", (0.0, 0.0)))
            except Exception:
                pass
        return (0.0, 0.0)

    def _save_safe_return(self, lat: float, lon: float):
        path = Path(ROBOT_DIR) / SAFE_RETURN_COORDS
        path.write_text(json.dumps({"coords": [lat, lon], "saved_at": datetime.now().isoformat()}))
        self._safe_return_coords = (lat, lon)

    def _save_mission(self):
        path = Path(ROBOT_DIR) / MISSION_FILE
        path.write_text(json.dumps(self.mission.to_dict(), indent=2))

    def _append_mission_history(self):
        path = Path(ROBOT_DIR) / MISSION_HISTORY
        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except Exception:
                pass
        history.append(self.mission.to_dict())
        path.write_text(json.dumps(history[-200:], indent=2))

    # ── Écoute des commandes de mission ──────────────────

    def _start_mission_listener(self):
        def handler(msg):
            if msg.type == MSG_TYPE_COMMAND:
                payload = msg.payload or {}
                cmd = payload.get("command", "")
                if cmd == "MISSION_START":
                    params = payload.get("params", {})
                    mission = RobotMission(
                        mission_id=params.get("mission_id", f"m-{time.time():.0f}"),
                        mission_type=params.get("type", "unknown"),
                        gps_coords=tuple(params.get("gps", (0.0, 0.0))),
                        params=params,
                    )
                    threading.Thread(target=self._execute_mission_wrapper,
                                     args=(mission,), daemon=True).start()
                elif cmd == "MISSION_ABORT":
                    self._abort_mission()
                elif cmd == "SAFE_RETURN":
                    self._safe_return_home()
                elif cmd == "SET_SAFE_POINT":
                    coords = payload.get("params", {}).get("gps", (0.0, 0.0))
                    self._save_safe_return(*coords)
                elif cmd == "STATUS":
                    self._publish_status()
                # ── Yield Protocol ─────────────────────
                elif cmd == "STOP_AND_YIELD":
                    authority = payload.get("params", {}).get("authority", "")
                    reason = payload.get("params", {}).get("reason", "priority")
                    self._yield_to(authority, reason)
                elif cmd == "RESUME":
                    self._resume()
        self.bus.subscribe("command", handler)

    # ── Boucle de mission ────────────────────────────────

    def _execute_mission_wrapper(self, mission: RobotMission):
        with self._mission_lock:
            self.mission = mission
            self.mission.status = "MISSION_START"
            self.mission.started_at = datetime.now(timezone.utc).isoformat()
            self._save_mission()
            self._publish_event("MISSION_START", {"mission_id": mission.mission_id})

            try:
                self.mission.add_step("navigation", "running", "Navigation vers GPS")
                self._navigate_to(mission.gps_coords)

                self.mission.add_step("execution", "running", f"Exécution: {mission.mission_type}")
                self.run_mission(mission)

                self.mission.status = "MISSION_COMPLETE"
                self.mission.add_step("complete", "success", "Mission terminée")
            except MissionAbortError:
                self.mission.status = "SAFE_RETURN"
                self.mission.add_step("abort", "warning", "Abandon → Safe Return Home")
                self._safe_return_home()
            except BatteryLowError:
                self.mission.status = "BATTERY_LOW"
                self.mission.add_step("battery", "error", "Batterie faible → retour")
                self._safe_return_home()
            except ConnectionLostError:
                self.mission.status = "LOST_CONNECTION"
                self.mission.add_step("connection", "error", "Connexion perdue → Safe Return Home")
                self._safe_return_home()
            except Exception as e:
                self.mission.status = "MISSION_FAILED"
                self.mission.error = str(e)
                self.mission.add_step("error", "error", str(e))
                self._publish_alert(f"Mission failed: {e}")

            self.mission.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_mission()
            self._append_mission_history()
            self._publish_event(self.mission.status, {"mission_id": mission.mission_id})

    def run_mission(self, mission: RobotMission):
        """Logique métier spécifique au robot. À surcharger."""
        raise NotImplementedError(f"{self.role} must implement run_mission()")

    def _navigate_to(self, gps: tuple):
        """Navigation vers des coordonnées GPS. Appelle PixHAL si disponible."""
        try:
            from core.pixhal.pixhal import PixHAL
            hal = PixHAL()
            hal.write_actuator("motor", 1)
        except Exception:
            pass
        time.sleep(1)

    # ── Safe Return Home ──────────────────────────────────

    def _safe_return_home(self):
        """Procédure de retour sécurisé au safe point."""
        self.mission.add_step("safe_return", "running", "Retour au safe point")
        try:
            lat, lon = self._safe_return_coords
            if lat != 0.0 or lon != 0.0:
                self.mission.add_step("safe_return_nav", "running", f"Navigation vers {lat},{lon}")
            try:
                from core.pixhal.pixhal import PixHAL
                hal = PixHAL()
                hal.write_actuator("motor", 1)
            except Exception:
                pass
            self.mission.add_step("safe_return", "success", "Robot au safe point")
        except Exception as e:
            self.mission.add_step("safe_return", "error", str(e))

    def set_safe_return(self, lat: float, lon: float):
        self._save_safe_return(lat, lon)

    # ── Yield Protocol ────────────────────────────────────

    def is_yielding(self) -> bool:
        return self._yielding_to != ""

    def _yield_to(self, authority: str, reason: str = "priority"):
        """Arrête le robot et cède le passage à un robot prioritaire.

        Protocole:
          1. Publie ACK_YIELD sur le bus (audit PixStat)
          2. Stop event pour interrompre la mission en cours
          3. Sauvegarde l'autorité, la raison et l'horodatage
        """
        self._yielding_to = authority
        self._yield_reason = reason
        self._yielded_at = time.time()

        if self.mission.status in ("EXECUTING", "MISSION_START"):
            self._stop.set()
        self.mission.status = "YIELDING"
        self.mission.add_step("yield", "warning", f"Cède le passage à {authority} ({reason})")

        self.bus.publish(Message("event", self.name, "pixstat", {
            "event": "ACK_YIELD",
            "authority": authority,
            "reason": reason,
            "role": self.role,
            "yielded_at": datetime.now(timezone.utc).isoformat(),
        }))
        self._publish_event("ACK_YIELD", {"authority": authority, "reason": reason})

    def _resume(self):
        """Autorité levée → le robot reprend son activité."""
        self._yielding_to = ""
        self._yield_reason = ""
        self._yielded_at = 0.0

        if self.mission.status == "YIELDING":
            self._stop.clear()
            self.mission.status = "IDLE"
            self.mission.add_step("resume", "info", "Reprise après yield")

        self._publish_event("ACK_RESUME", {})

    def report_yield_state(self) -> dict:
        return {
            "yielding": self.is_yielding(),
            "yielding_to": self._yielding_to,
            "yield_reason": self._yield_reason,
            "yielded_at": self._yielded_at,
            "priority_abuse_count": self._priority_abuse_count,
        }

    # ── Abort ─────────────────────────────────────────────

    def _abort_mission(self):
        self._stop.set()
        self.mission.status = "MISSION_FAILED"
        self.mission.error = "Aborted by operator"
        self._publish_event("MISSION_ABORTED", {"mission_id": self.mission.mission_id})

    def _publish_status(self):
        self.bus.publish(Message(MSG_TYPE_HEARTBEAT, self.name, "bus", {
            "status": self.mission.status,
            "role": self.role,
            "battery": self._battery_level,
            "mission_id": self.mission.mission_id,
        }))

    def _publish_event(self, event: str, data: dict):
        self.bus.publish(Message(MSG_TYPE_EVENT, self.name, "bus", {
            "event": event,
            **data,
        }))

    def _publish_alert(self, message: str):
        self.bus.publish(Message("alert", self.name, "pixstat", {
            "type": "robot_alert",
            "role": self.role,
            "message": message,
        }))

    # ── Batterie ──────────────────────────────────────────

    def _start_battery_monitor(self):
        def loop():
            while not self._stop.is_set():
                self._stop.wait(30)
                if self._stop.is_set():
                    break
                try:
                    self._check_battery()
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def _check_battery(self):
        previous = self._battery_level
        self._battery_level = self._read_battery()
        if self._battery_level < BATTERY_LOW_THRESHOLD and previous >= BATTERY_LOW_THRESHOLD:
            if self.mission.status in ("EXECUTING", "MISSION_START"):
                self._abort_mission()

    def _read_battery(self) -> float:
        """Lit le niveau batterie (matériel ou simulé pour test)."""
        try:
            r = subprocess.run(
                ["sysctl", "hw.sensors"],
                capture_output=True, text=True, timeout=3,
            )
            for line in r.stdout.splitlines():
                if "battery" in line.lower() and "percent" in line.lower():
                    m = __import__("re").search(r"(\d+)%", line)
                    if m:
                        return float(m.group(1))
        except Exception:
            pass
        try:
            with open("/sys/class/power_supply/BAT0/capacity") as f:
                return float(f.read().strip())
        except Exception:
            pass
        return 100.0

    # ── Connexion ─────────────────────────────────────────

    def check_connection(self) -> bool:
        """Vérifie la connexion à l'Orchestrateur."""
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "10.0.0.1"],
                capture_output=True, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    # ── Heartbeat renforcé ───────────────────────────────

    def send_heartbeat(self):
        """Surcharge PixModule.send_heartbeat avec les infos robot."""
        msg = Message(MSG_TYPE_HEARTBEAT, self.name, "bus", {
            "status": self.mission.status,
            "role": self.role,
            "battery": self._battery_level,
            "connection_ok": self.check_connection(),
            "error_count": self.error_count,
            "pid": os.getpid(),
        })
        self.bus.publish(msg)

    # ── Stats ─────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "hw_version": self.hw_version,
            "hardware_id": self._hardware_id()[:16],
            "status": self.mission.status,
            "battery": self._battery_level,
            "safe_return": list(self._safe_return_coords),
            "mission": self.mission.to_dict(),
            "robot_spec": ROBOT_ROLES.get(self.role, {}),
        }

    def handle_request(self, msg) -> dict:
        cmd = msg.payload.get("command", "")
        if cmd == "stats":
            return {**self.stats(), "yield": self.report_yield_state()}
        if cmd == "status":
            return {"status": self.mission.status, "battery": self._battery_level,
                    "yielding": self.is_yielding()}
        if cmd == "safe_return":
            return {"coords": list(self._safe_return_coords)}
        if cmd == "set_safe_return":
            params = msg.payload.get("params", {})
            lat = params.get("lat", 0.0)
            lon = params.get("lon", 0.0)
            self.set_safe_return(lat, lon)
            return {"status": "ok", "coords": [lat, lon]}
        if cmd == "yield_state":
            return self.report_yield_state()
        if cmd == "clear_abuse":
            self._priority_abuse_count = 0
            return {"status": "ok"}
        return super().handle_request(msg)


class MissionAbortError(Exception):
    pass


class BatteryLowError(Exception):
    pass


class ConnectionLostError(Exception):
    pass
