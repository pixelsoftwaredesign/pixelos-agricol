"""
DronePilot — Robot aérien inspecteur.
Hérite de RobotNode avec capacités de vol MAVLink et droit
de priorité sur les robots au sol.
"""

import threading

from robots.base import RobotNode
from core.ipc import Message, MSG_TYPE_COMMAND, PRIORITY_HIGH, PRIORITY_CRITICAL
from core.traffic import (
    RightOfWay, TRAFFIC_CMD_STOP, TRAFFIC_CMD_YIELD, TRAFFIC_CMD_RESUME,
    TRAFFIC_CMD_OVERRIDE, ROLE_PRIORITY,
)


class DronePilot(RobotNode):
    def __init__(self, name: str):
        super().__init__(name, role="INSPECTEUR")
        self.altitude = 0.0
        self.target_altitude = 0.0
        self.position = (0.0, 0.0)
        self._flight_lock = threading.Lock()
        self._hover_stop = threading.Event()

    # ── API de vol ─────────────────────────────────────────

    def arm(self) -> dict:
        """Arme les moteurs du drone."""
        self.status = "RUNNING"
        return {"status": "ok", "armed": True}

    def disarm(self) -> dict:
        self.status = "IDLE"
        return {"status": "ok", "armed": False}

    def takeoff(self, altitude: float) -> dict:
        """Décollage et stabilisation à altitude mètres."""
        if altitude < 0.5 or altitude > 120:
            return {"status": "error", "reason": "altitude hors limites (0.5-120m)"}
        with self._flight_lock:
            self.target_altitude = altitude
            self.altitude = altitude
        return {"status": "ok", "altitude": self.altitude}

    def land(self) -> dict:
        """Atterrissage."""
        with self._flight_lock:
            self.altitude = 0.0
        return {"status": "ok", "altitude": 0}

    def fly_to(self, x: float, y: float, z: float = None) -> dict:
        """Vol vers des coordonnées 3D."""
        if z is not None:
            alt_cmd = self.takeoff(z)
            if alt_cmd.get("status") != "ok":
                return alt_cmd
        with self._flight_lock:
            self.position = (x, y)
        return {"status": "ok", "position": list(self.position)}

    def hover(self) -> dict:
        """Maintien sur place."""
        return {"status": "ok", "altitude": self.altitude}

    def get_flight_status(self) -> dict:
        return {
            "position": list(self.position),
            "altitude": self.altitude,
            "target_altitude": self.target_altitude,
            "speed": 0,
            "battery": self.battery,
        }

    # ── Priorité / Override robots au sol ─────────────────

    def override_ground_robot(self, robot_id: str, reason: str = "inspection") -> bool:
        """Envoie un ordre STOP prioritaire à un robot au sol."""
        msg = Message(
            MSG_TYPE_COMMAND, self.name, robot_id,
            payload={
                "command": TRAFFIC_CMD_OVERRIDE,
                "params": {"reason": reason, "authority": self.role},
            },
            priority=PRIORITY_CRITICAL,
        )
        self.bus.publish(msg)
        return True

    def clear_ground_robot(self, robot_id: str) -> bool:
        """Lève l'override et autorise la reprise."""
        msg = Message(
            MSG_TYPE_COMMAND, self.name, robot_id,
            payload={
                "command": TRAFFIC_CMD_RESUME,
                "params": {"reason": "override_cleared"},
            },
            priority=PRIORITY_HIGH,
        )
        self.bus.publish(msg)
        return True

    # ── Scan aérien ────────────────────────────────────────

    def aerial_scan(self, zone: tuple) -> dict:
        """Survole une zone pour inspection."""
        x1, y1, x2, y2 = zone
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        self.fly_to(cx, cy, 15.0)
        self.hover()
        result = {
            "status": "ok",
            "zone": zone,
            "position": list(self.position),
            "altitude": self.altitude,
            "scan": "ok",
        }
        return result

    # ── Cycle de vie mission ───────────────────────────────

    def run_mission(self, mission) -> dict:
        step = mission.payload.get("step", "scan")
        if step == "scan":
            zone = mission.payload.get("zone", (0, 0, 10, 10))
            return self.aerial_scan(zone)
        elif step == "fly":
            target = mission.payload.get("target", (0, 0))
            alt = mission.payload.get("altitude", 10)
            return self.fly_to(target[0], target[1], alt)
        elif step == "override":
            robot_id = mission.payload.get("robot_id", "")
            return {"status": "ok", "override": self.override_ground_robot(robot_id)}
        return {"status": "error", "reason": f"step inconnu: {step}"}

    # ── Surcharge handle_request pour commandes de vol ────

    def handle_request(self, msg) -> dict:
        cmd = msg.payload.get("command", "")
        params = msg.payload.get("params", {})

        if cmd == "arm":
            return self.arm()
        elif cmd == "disarm":
            return self.disarm()
        elif cmd == "takeoff":
            return self.takeoff(params.get("altitude", 10))
        elif cmd == "land":
            return self.land()
        elif cmd == "fly_to":
            return self.fly_to(
                params.get("x", 0), params.get("y", 0),
                params.get("z", None),
            )
        elif cmd == "hover":
            return self.hover()
        elif cmd == "flight_status":
            return self.get_flight_status()
        elif cmd == "aerial_scan":
            return self.aerial_scan(tuple(params.get("zone", (0, 0, 10, 10))))
        elif cmd == "override_ground":
            return {"status": "ok", "sent": self.override_ground_robot(
                params.get("robot_id", ""),
                params.get("reason", "inspection"),
            )}
        elif cmd == "clear_ground":
            return {"status": "ok", "sent": self.clear_ground_robot(
                params.get("robot_id", ""),
            )}

        return super().handle_request(msg)
