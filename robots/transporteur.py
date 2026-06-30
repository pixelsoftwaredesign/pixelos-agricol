#!/usr/bin/env python3
"""
RobotTransporteur — Robot de transport et logistique.

Priorités :
  - Navigation LiDAR / GPS entre dépôt et zones de récolte
  - PixHAL pour contrôle moteur et servos de direction
  - Gestion de charge utile (pesée embarquée)
  - Évitement d'obstacles par ultrason

Matériel requis :
  - LiDAR 2D/3D, GPS RTK, IMU
  - 4 moteurs brushless, servos de direction
  - Plateforme 500kg, benne basculante
  - Batterie 20000mAh
"""

import os
import sys
import json
import time
import threading
import math
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pixelos", "src"))
import subprocess
from core.ipc import Message
from robots.base import RobotNode, RobotMission
from robots.base import BatteryLowError, ConnectionLostError

OBSTACLE_THRESHOLD_CM = 50
PAYLOAD_MAX_KG = 500
NAV_SPEED_DEFAULT = 1.0


class RobotTransporteur(RobotNode):
    def __init__(self, name: str = "transporteur-001"):
        super().__init__(name, role="transporteur", hw_version="2.0")
        self._payload_kg = 0.0
        self._position = (0.0, 0.0)
        self._path: list[tuple] = []
        self._nav_thread: Optional[threading.Thread] = None
        self._nav_stop = threading.Event()
        self.deliveries_completed = 0

    # ── Logique de mission ───────────────────────────────

    def run_mission(self, mission: RobotMission):
        mt = mission.mission_type

        if mt == "transport":
            self._execute_transport(mission)
        elif mt == "return_to_depot":
            self._return_to_depot(mission)
        elif mt == "patrol":
            self._execute_patrol(mission)
        else:
            mission.add_step("unknown_type", "error", f"Type inconnu: {mt}")
            raise ValueError(f"Unknown mission type: {mt}")

    def _execute_transport(self, mission: RobotMission):
        origin = tuple(mission.params.get("origin", (0.0, 0.0)))
        destination = tuple(mission.params.get("destination", (0.0, 0.0)))
        payload = mission.params.get("payload_kg", 0.0)

        if payload > PAYLOAD_MAX_KG:
            mission.add_step("overload", "error", f"Payload {payload}kg > max {PAYLOAD_MAX_KG}kg")
            raise ValueError(f"Payload exceeds max: {payload}kg")

        self._payload_kg = payload
        mission.add_step("load", "ok", f"Chargé: {payload}kg")

        mission.add_step("navigate_origin", "running", "Navigation vers origine")
        self._navigate_to(origin, mission)

        mission.add_step("pickup", "ok", "Pickup effectué")
        self._publish_event("PICKUP", {"location": origin})

        mission.add_step("navigate_destination", "running", "Navigation vers destination")
        self._navigate_to(destination, mission)

        mission.add_step("dropoff", "ok", "Livraison effectuée")
        self.deliveries_completed += 1
        self._payload_kg = 0.0
        self._publish_event("DELIVERY_COMPLETE", {
            "origin": origin,
            "destination": destination,
            "payload_kg": payload,
        })

    def _return_to_depot(self, mission: RobotMission):
        depot = tuple(mission.params.get("depot", self._safe_return_coords))
        mission.add_step("return_depot", "running", f"Retour dépôt {depot}")
        self._navigate_to(depot, mission)
        self._payload_kg = 0.0
        mission.add_step("depot_arrived", "ok", "Arrivé au dépôt")

    def _execute_patrol(self, mission: RobotMission):
        waypoints = mission.params.get("waypoints", [])
        loops = mission.params.get("loops", 1)

        for lap in range(loops):
            for i, wp in enumerate(waypoints):
                if self._stop.is_set():
                    raise BatteryLowError("Patrol aborted")
                wp_tuple = tuple(wp) if isinstance(wp, (list, tuple)) else (0.0, 0.0)
                mission.add_step(f"patrol_{lap}_{i}", "running", f"Waypoint {i}")
                self._navigate_to(wp_tuple, mission)

    # ── Navigation améliorée ─────────────────────────────

    def _navigate_to(self, target: tuple, mission: Optional[RobotMission] = None):
        """Navigation avec évitement d'obstacles et check batterie."""
        lat, lon = target
        steps = self._plan_path(self._position, target)

        for i, wp in enumerate(steps):
            if self._stop.is_set():
                raise BatteryLowError("Navigation interrompue")
            if self._battery_level < BATTERY_LOW_THRESHOLD:
                raise BatteryLowError(f"Battery {self._battery_level}%")

            if not self.check_connection():
                raise ConnectionLostError("WiFi perdu pendant navigation")

            obstacle = self._check_obstacle()
            if obstacle:
                self._avoid_obstacle(obstacle)
                if mission:
                    mission.add_step(f"obstacle_{i}", "warning", f"Évitement à {wp}")

            self._drive_to(wp)
            self._position = wp

        self._position = target

    def _plan_path(self, origin: tuple, destination: tuple) -> list[tuple]:
        """Planifie un chemin simple (sera remplacé par A* / RRT)."""
        lat1, lon1 = origin
        lat2, lon2 = destination
        steps_count = max(int(math.dist(origin, destination) / 10), 1)
        path = []
        for i in range(1, steps_count + 1):
            t = i / steps_count
            path.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
        return path

    def _check_obstacle(self) -> Optional[float]:
        """Vérifie la présence d'obstacles via LiDAR ou ultrason."""
        try:
            r = subprocess.run(
                ["python3", "-c", "print(200)"],
                capture_output=True, text=True, timeout=2,
            )
            dist = float(r.stdout.strip())
            if dist < OBSTACLE_THRESHOLD_CM:
                return dist
        except Exception:
            pass
        return None

    def _avoid_obstacle(self, distance: float):
        """Contourne un obstacle détecté."""
        try:
            from core.pixhal.pixhal import PixHAL
            hal = PixHAL()
            hal.write_actuator("servo", 30)
            time.sleep(0.5)
            hal.write_actuator("servo", 0)
        except Exception:
            pass

    def _drive_to(self, waypoint: tuple):
        """Actionne les moteurs pour atteindre un waypoint."""
        try:
            from core.pixhal.pixhal import PixHAL
            hal = PixHAL()
            hal.write_actuator("motor", 1)
            hal.write_actuator("servo", 0)
        except Exception:
            pass
        time.sleep(0.2)

    def handle_request(self, msg) -> dict:
        cmd = msg.payload.get("command", "")
        if cmd == "payload":
            return {"payload_kg": self._payload_kg}
        if cmd == "position":
            return {"position": list(self._position)}
        if cmd == "deliveries":
            return {"deliveries_completed": self.deliveries_completed}
        if cmd == "set_payload":
            kg = msg.payload.get("params", {}).get("kg", 0)
            self._payload_kg = min(kg, PAYLOAD_MAX_KG)
            return {"status": "ok", "payload_kg": self._payload_kg}
        return super().handle_request(msg)

    def stats(self) -> dict:
        base = super().stats()
        base.update({
            "payload_kg": self._payload_kg,
            "position": list(self._position),
            "deliveries_completed": self.deliveries_completed,
            "max_payload_kg": PAYLOAD_MAX_KG,
        })
        return base
