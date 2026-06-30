"""
TrafficController — Gestion centralisée du trafic et des collisions.

S'intègre à PixOrchestrator pour maintenir une carte des positions,
détecter les conflits et ordonner les priorités entre robots.
"""

import time
import threading
from datetime import datetime, timezone
from collections import defaultdict

from core.ipc import (
    MessageBus, Message, MSG_TYPE_COMMAND, MSG_TYPE_EVENT,
    PRIORITY_HIGH, PRIORITY_CRITICAL,
)
from core.traffic import (
    RightOfWay, TRAFFIC_CMD_STOP, TRAFFIC_CMD_YIELD, TRAFFIC_CMD_RESUME,
    TRAFFIC_CMD_OVERRIDE, TRAFFIC_CMD_HOLD_POSITION, ROLE_PRIORITY,
)


class TrafficController:
    """Maintient la carte des positions et résout les conflits de circulation.

    Usage (intégré à PixOrchestrator):
        tc = TrafficController()
        orchestrator.register_hook("after_node_join", tc.register_robot)
        tc.start()
    """

    CHECK_INTERVAL = 1.0
    COLLISION_THRESHOLD = 2.0
    ZONE_MARGIN = 1.0

    def __init__(self):
        self.bus = MessageBus()
        self._robots: dict[str, dict] = {}
        self._zones: dict[str, tuple] = {}
        self._hold_map: dict[str, str] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._log = []

    # ── Gestion des robots ────────────────────────────────

    def register_robot(self, node_id: str, role: str, position=(0.0, 0.0)):
        with self._lock:
            self._robots[node_id] = {
                "node_id": node_id,
                "role": role,
                "position": position,
                "status": "idle",
                "priority": ROLE_PRIORITY.get(role, 0),
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_update": time.time(),
            }

    def unregister_robot(self, node_id: str):
        with self._lock:
            self._robots.pop(node_id, None)
            self._zones.pop(node_id, None)
            self._hold_map.pop(node_id, None)

    def update_position(self, node_id: str, position: tuple):
        with self._lock:
            if node_id in self._robots:
                self._robots[node_id]["position"] = position
                self._robots[node_id]["last_update"] = time.time()

    def reserve_zone(self, node_id: str, zone: tuple):
        with self._lock:
            self._zones[node_id] = zone

    def release_zone(self, node_id: str):
        with self._lock:
            self._zones.pop(node_id, None)

    # ── Détection de conflits ─────────────────────────────

    def _detect_collisions(self) -> list[dict]:
        conflicts = []
        robots = list(self._robots.items())
        for i in range(len(robots)):
            for j in range(i + 1, len(robots)):
                ni, ri = robots[i]
                nj, rj = robots[j]
                if RightOfWay.collision_risk(
                    ri["position"], rj["position"], self.COLLISION_THRESHOLD,
                ):
                    conflicts.append({
                        "a": ni, "a_role": ri["role"],
                        "b": nj, "b_role": rj["role"],
                        "a_pos": ri["position"],
                        "b_pos": rj["position"],
                        "type": "proximity",
                    })
                zi = self._zones.get(ni)
                zj = self._zones.get(nj)
                if zi and zj and RightOfWay.overlap_zones(zi, zj):
                    conflicts.append({
                        "a": ni, "a_role": ri["role"],
                        "b": nj, "b_role": rj["role"],
                        "zone_a": zi, "zone_b": zj,
                        "type": "zone_overlap",
                    })
        return conflicts

    def _resolve_conflict(self, conflict: dict):
        r_a = self._robots.get(conflict["a"])
        r_b = self._robots.get(conflict["b"])
        if not r_a or not r_b:
            return

        priority_a = ROLE_PRIORITY.get(r_a["role"], 0)
        priority_b = ROLE_PRIORITY.get(r_b["role"], 0)

        if priority_a >= priority_b:
            winner, loser = conflict["a"], conflict["b"]
        else:
            winner, loser = conflict["b"], conflict["a"]

        loser_role = self._robots[loser]["role"]
        self._send_traffic_command(
            loser, TRAFFIC_CMD_HOLD_POSITION,
            {"reason": "collision_avoidance", "authority": winner},
        )
        self._hold_map[loser] = winner
        self._log_event("collision", f"{loser}({loser_role}) cède à {winner}")

    def _send_traffic_command(self, target: str, command: str, params: dict):
        self.bus.send_command(target, command, params, priority=PRIORITY_CRITICAL)

    # ── Boucle ────────────────────────────────────────────

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            conflicts = self._detect_collisions()
            for c in conflicts:
                self._resolve_conflict(c)
            self._check_recovery()
            self._stop.wait(self.CHECK_INTERVAL)

    def _check_recovery(self):
        """Lève les holds si le winner n'est plus à proximité."""
        now = time.time()
        to_release = []
        for loser, winner in self._hold_map.items():
            rw = self._robots.get(winner)
            rl = self._robots.get(loser)
            if not rw or not rl:
                to_release.append(loser)
                continue
            if not RightOfWay.collision_risk(
                rw["position"], rl["position"], self.COLLISION_THRESHOLD * 2,
            ):
                to_release.append(loser)
        for loser in to_release:
            self._send_traffic_command(loser, TRAFFIC_CMD_RESUME, {"reason": "clear"})
            self._hold_map.pop(loser, None)
            self._log_event("clear", f"{loser} libéré")

    # ── Stats / Rapports ──────────────────────────────────

    def _log_event(self, event: str, detail: str):
        self._log.append({
            "event": event,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._log) > 1000:
            self._log = self._log[-500:]

    def stats(self) -> dict:
        with self._lock:
            return {
                "robots_tracked": len(self._robots),
                "active_holds": len(self._hold_map),
                "zones_reserved": len(self._zones),
                "conflict_log_size": len(self._log),
                "robots": {
                    n: {
                        "role": r["role"],
                        "position": list(r["position"]),
                        "status": r["status"],
                        "priority": r["priority"],
                    }
                    for n, r in self._robots.items()
                },
                "holds": dict(self._hold_map),
            }
