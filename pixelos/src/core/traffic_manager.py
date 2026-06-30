"""
TrafficManager — Règles de circulation complètes PixRobots.

Applique le Code de la Route :
  - Hiérarchie INSPECTEUR > RÉCOLTEUR > TRANSPORTEUR
  - Distance de sécurité sol > 1.5m, altitude drone > 2.5m
  - Détection d'abus de priorité → révocation PixOrchestrator
  - ROUTING_ADJUST pour déviation des robots au sol
"""

import time
import threading
from datetime import datetime, timezone

from core.ipc import (
    MessageBus, Message, MSG_TYPE_COMMAND, MSG_TYPE_EVENT,
    PRIORITY_HIGH, PRIORITY_CRITICAL,
)
from core.traffic import RightOfWay, ROLE_PRIORITY, Priority


# Règles de séparation (mètres)
SEPARATION_GROUND_MIN = 1.5
SEPARATION_DRONE_ALT_MIN = 2.5
ABUSE_LIMIT = 5
ABUSE_WINDOW = 300  # secondes


class TrafficManager:
    """Ordonnanceur central du trafic.

    Usage:
        tm = TrafficManager()
        tm.start()
        # appelé par PixOrchestrator.register_robot / update_position
    """

    CHECK_INTERVAL = 1.0

    def __init__(self):
        self.bus = MessageBus()
        self._robots: dict[str, dict] = {}
        self._zones: dict[str, tuple] = {}
        self._hold_map: dict[str, str] = {}
        self._abuse_log: dict[str, list[float]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._events: list[dict] = []

    # ── API publique ─────────────────────────────────────

    def register_robot(self, node_id: str, role: str, position=(0.0, 0.0), altitude=0.0):
        with self._lock:
            self._robots[node_id] = {
                "node_id": node_id,
                "role": role,
                "position": position,
                "altitude": altitude,
                "status": "idle",
                "priority": ROLE_PRIORITY.get(role, 0),
                "is_drone": role.upper() == "INSPECTEUR",
                "abuse_count": 0,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_update": time.time(),
            }

    def unregister_robot(self, node_id: str):
        with self._lock:
            self._robots.pop(node_id, None)
            self._zones.pop(node_id, None)
            self._hold_map.pop(node_id, None)
            self._abuse_log.pop(node_id, None)

    def update_position(self, node_id: str, position: tuple, altitude: float = None):
        with self._lock:
            r = self._robots.get(node_id)
            if r:
                r["position"] = position
                if altitude is not None:
                    r["altitude"] = altitude
                r["last_update"] = time.time()

    def reserve_zone(self, node_id: str, zone: tuple):
        with self._lock:
            self._zones[node_id] = zone

    def release_zone(self, node_id: str):
        with self._lock:
            self._zones.pop(node_id, None)

    # ── Règles de séparation ─────────────────────────────

    def _check_separation(self, a: dict, b: dict) -> list[dict]:
        """Vérifie les règles de distance minimale."""
        violations = []

        # Règle sol : distance > 1.5m
        dx = a["position"][0] - b["position"][0]
        dy = a["position"][1] - b["position"][1]
        ground_dist = (dx * dx + dy * dy) ** 0.5

        if not a["is_drone"] and not b["is_drone"]:
            if ground_dist < SEPARATION_GROUND_MIN:
                violations.append({
                    "a": a["node_id"], "b": b["node_id"],
                    "rule": "ground_separation",
                    "distance": round(ground_dist, 2),
                    "required": SEPARATION_GROUND_MIN,
                })

        # Règle drone : altitude > 2.5m quand au-dessus d'un robot sol
        if a["is_drone"] and not b["is_drone"] and ground_dist < SEPARATION_GROUND_MIN * 2:
            if a["altitude"] < SEPARATION_DRONE_ALT_MIN:
                violations.append({
                    "a": a["node_id"], "b": b["node_id"],
                    "rule": "drone_altitude",
                    "altitude": a["altitude"],
                    "required": SEPARATION_DRONE_ALT_MIN,
                })
        if b["is_drone"] and not a["is_drone"] and ground_dist < SEPARATION_GROUND_MIN * 2:
            if b["altitude"] < SEPARATION_DRONE_ALT_MIN:
                violations.append({
                    "a": b["node_id"], "b": a["node_id"],
                    "rule": "drone_altitude",
                    "altitude": b["altitude"],
                    "required": SEPARATION_DRONE_ALT_MIN,
                })

        return violations

    # ── Résolution des conflits ──────────────────────────

    def _detect_and_resolve(self):
        robots = list(self._robots.items())
        resolved = []

        for i in range(len(robots)):
            for j in range(i + 1, len(robots)):
                ni, ri = robots[i]
                nj, rj = robots[j]

                # 1. Collision immédiate
                if RightOfWay.collision_risk(ri["position"], rj["position"], SEPARATION_GROUND_MIN):
                    if ROLE_PRIORITY.get(ri["role"], 0) >= ROLE_PRIORITY.get(rj["role"], 0):
                        loser, winner = nj, ni
                    else:
                        loser, winner = ni, nj
                    self._send_stop_and_yield(loser, winner, "collision")
                    self._hold_map[loser] = winner
                    resolved.append((loser, winner, "collision"))

                # 2. Chevauchement de zone
                zi = self._zones.get(ni)
                zj = self._zones.get(nj)
                if zi and zj and RightOfWay.overlap_zones(zi, zj):
                    if ROLE_PRIORITY.get(ri["role"], 0) >= ROLE_PRIORITY.get(rj["role"], 0):
                        loser_zone, winner_zone = nj, ni
                    else:
                        loser_zone, winner_zone = ni, nj
                    self._send_stop_and_yield(loser_zone, winner_zone, "zone_overlap")
                    self._hold_map[loser_zone] = winner_zone
                    resolved.append((loser_zone, winner_zone, "zone_overlap"))

                # 3. Violation séparation
                for v in self._check_separation(ri, rj):
                    if v["rule"] == "drone_altitude":
                        violator = v["a"]
                        self._send_altitude_correction(violator, v["required"])
                    elif v["rule"] == "ground_separation":
                        if ROLE_PRIORITY.get(ri["role"], 0) >= ROLE_PRIORITY.get(rj["role"], 0):
                            self._send_stop_and_yield(v["b"], v["a"], "separation")
                            self._hold_map[v["b"]] = v["a"]
                        else:
                            self._send_stop_and_yield(v["a"], v["b"], "separation")
                            self._hold_map[v["a"]] = v["b"]
                    resolved.append(v)

        return resolved

    # ── Envoi des commandes ──────────────────────────────

    def _send_stop_and_yield(self, target: str, authority: str, reason: str):
        self._log_event("STOP_AND_YIELD", f"{target} cède à {authority} ({reason})")
        self.bus.send_command(target, "STOP_AND_YIELD", {
            "authority": authority,
            "reason": reason,
        }, priority=PRIORITY_CRITICAL)

    def _send_resume(self, target: str):
        self._log_event("RESUME", f"{target} libéré")
        self.bus.send_command(target, "RESUME", {}, priority=PRIORITY_HIGH)

    def _send_altitude_correction(self, target: str, min_alt: float):
        self._log_event("ALTITUDE_CORRECTION", f"{target} doit monter à >{min_alt}m")
        self.bus.send_command(target, "ALTITUDE_SET", {
            "min_altitude": min_alt,
        }, priority=PRIORITY_HIGH)

    def _send_routing_adjust(self, target: str, avoid_node: str):
        """Dévie un robot au sol pour contourner un blocage."""
        self._log_event("ROUTING_ADJUST", f"{target} dévié (évite {avoid_node})")
        self.bus.send_command(target, "ROUTING_ADJUST", {
            "avoid_node": avoid_node,
        }, priority=PRIORITY_HIGH)

    # ── Détection d'abus ─────────────────────────────────

    def record_override(self, inspector_id: str):
        """Enregistre une demande d'override pour détection d'abus."""
        now = time.time()
        with self._lock:
            if inspector_id not in self._abuse_log:
                self._abuse_log[inspector_id] = []
            self._abuse_log[inspector_id].append(now)
            # Fenêtre glissante
            self._abuse_log[inspector_id] = [
                t for t in self._abuse_log[inspector_id]
                if now - t < ABUSE_WINDOW
            ]
            count = len(self._abuse_log[inspector_id])
            r = self._robots.get(inspector_id)
            if r:
                r["abuse_count"] = count
            if count >= ABUSE_LIMIT:
                self._revoke_priority(inspector_id)

    def _revoke_priority(self, node_id: str):
        """Révoque le privilège de priorité pour cause d'abus."""
        try:
            self._log_event("REVOKE", f"Priorité révoquée pour {node_id} ({ABUSE_LIMIT} overrides en {ABUSE_WINDOW}s)")
            self.bus.send_command(node_id, "PRIORITY_REVOKE", {
                "reason": "abuse",
                "abuse_count": ABUSE_LIMIT,
            }, priority=PRIORITY_CRITICAL)
        except Exception:
            pass
        with self._lock:
            r = self._robots.get(node_id)
            if r:
                r["priority"] = 0
                r["status"] = "revoked"

    # ── Boucle principale ────────────────────────────────

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            resolved = self._detect_and_resolve()
            self._check_recovery()
            self._stop.wait(self.CHECK_INTERVAL)

    def _check_recovery(self):
        """Lève les holds si la zone est libre."""
        now = time.time()
        to_release = []
        for loser, winner in self._hold_map.items():
            rw = self._robots.get(winner)
            rl = self._robots.get(loser)
            if not rw or not rl:
                to_release.append(loser)
                continue
            dx = rw["position"][0] - rl["position"][0]
            dy = rw["position"][1] - rl["position"][1]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > SEPARATION_GROUND_MIN * 3:
                to_release.append(loser)
        for loser in to_release:
            self._send_resume(loser)
            self._hold_map.pop(loser, None)

    # ── Événements / Stats ───────────────────────────────

    def _log_event(self, event: str, detail: str):
        entry = {"event": event, "detail": detail,
                 "timestamp": datetime.now(timezone.utc).isoformat()}
        self._events.append(entry)
        if len(self._events) > 2000:
            self._events = self._events[-1000:]
        try:
            self.bus.publish(Message(MSG_TYPE_EVENT, "traffic_manager", "pixstat", entry))
        except Exception:
            pass

    def stats(self) -> dict:
        with self._lock:
            return {
                "robots_tracked": len(self._robots),
                "active_holds": len(self._hold_map),
                "zones_reserved": len(self._zones),
                "events_logged": len(self._events),
                "abuses": {n: len(ts) for n, ts in self._abuse_log.items()},
                "robots": {
                    n: {
                        "role": r["role"],
                        "position": list(r["position"]),
                        "altitude": r.get("altitude", 0),
                        "status": r["status"],
                        "priority": r["priority"],
                        "abuse_count": r.get("abuse_count", 0),
                        "is_drone": r.get("is_drone", False),
                    }
                    for n, r in self._robots.items()
                },
                "holds": dict(self._hold_map),
            }
