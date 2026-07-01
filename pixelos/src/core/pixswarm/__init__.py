"""
PixSwarm — Orchestrateur d'essaim robotique.

Coordonne les robots via PixDDS pour :
  - Formation (Flying-V, Grid, Line, Loose)
  - Heartbeat / health monitoring
  - Topologie dynamique (join/leave)
  - Élection de leader
  - Broadcast d'urgence

Usage:
    from core.pixswarm import PixSwarm

    swarm = PixSwarm(
        domain_id=0,
        node_id="robot_01",
        role="drone",
        formation="flying_v"
    )
    swarm.start()
    # ... robot boucle ...
    swarm.update_heartbeat(battery=85, load_avg=0.3)
    swarm.stop()
"""

import json
import time
import threading
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from core.pixdds import (
    create_participant, DomainParticipant,
    Topic, DataWriter, DataReader,
)


# ── Constants ──────────────────────────────────────────────

HEARTBEAT_TOPIC = "/swarm/heartbeat"
FORMATION_TOPIC = "/swarm/formation"
EMERGENCY_TOPIC = "/swarm/emergency"
LEADER_TOPIC = "/swarm/leader"
HEARTBEAT_INTERVAL = 2.0
LEADER_TIMEOUT = 8.0


# ── Enums ──────────────────────────────────────────────────

class FormationType(Enum):
    FLYING_V = "flying_v"
    GRID = "grid"
    LINE = "line"
    LOOSE = "loose"

    @classmethod
    def offsets(cls, ftype: str, count: int, index: int) -> tuple[float, float, float]:
        """Calcule le décalage (dx, dy, dz) pour un robot dans une formation.

        Retourne le décalage relatif au leader.
        """
        if ftype == "flying_v":
            wing = index // 2 + 1
            side = -1 if index % 2 == 0 else 1
            return (side * wing * 2.0, 0.0, -wing * 1.5)
        elif ftype == "grid":
            cols = max(2, int(count ** 0.5))
            row = index // cols
            col = index % cols
            return (col * 3.0, row * 3.0, 0.0)
        elif ftype == "line":
            return (0.0, 0.0, -index * 2.0)
        else:  # loose
            return (random.uniform(-5, 5), random.uniform(-5, 5), 0.0)


class NodeRole(Enum):
    DRONE = "drone"
    GROUND = "ground"
    GATEWAY = "gateway"


class NodeStatus(Enum):
    ONLINE = "online"
    STALE = "stale"
    OFFLINE = "offline"
    EMERGENCY = "emergency"


# ── Data classes ───────────────────────────────────────────

@dataclass
class SwarmHeartbeat:
    node_id: str
    role: str
    domain_id: int
    timestamp: float = 0.0
    battery: int = -1
    load_avg: float = 0.0
    position: tuple = (0.0, 0.0, 0.0)
    formation_slot: int = -1

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "domain_id": self.domain_id,
            "timestamp": self.timestamp or time.monotonic(),
            "battery": self.battery,
            "load_avg": round(self.load_avg, 2),
            "position": list(self.position),
            "formation_slot": self.formation_slot,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SwarmHeartbeat":
        pos = tuple(d.get("position", [0, 0, 0]))
        return cls(
            node_id=d["node_id"],
            role=d.get("role", "drone"),
            domain_id=d.get("domain_id", 0),
            timestamp=d.get("timestamp", 0),
            battery=d.get("battery", -1),
            load_avg=d.get("load_avg", 0.0),
            position=pos,
            formation_slot=d.get("formation_slot", -1),
        )


@dataclass
class FormationOrder:
    ftype: str
    leader_id: str
    members: list[str] = field(default_factory=list)
    speed: float = 1.0
    altitude: float = 10.0

    def to_dict(self) -> dict:
        return {
            "type": "FORMATION_ORDER",
            "ftype": self.ftype,
            "leader_id": self.leader_id,
            "members": self.members,
            "speed": self.speed,
            "altitude": self.altitude,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FormationOrder":
        return cls(
            ftype=d.get("ftype", "loose"),
            leader_id=d.get("leader_id", ""),
            members=d.get("members", []),
            speed=d.get("speed", 1.0),
            altitude=d.get("altitude", 10.0),
        )


# ── PixSwarm ───────────────────────────────────────────────

class PixSwarm:
    """Orchestrateur d'essaim.

    Chaque nœud de l'essaim instancie PixSwarm avec son rôle.
    L'orchestrateur gère automatiquement :
      - Heartbeat périodique sur PixDDS
      - Détection des pairs
      - Élection de leader (premier arrivé, ou plus forte batterie)
      - Calcul de position dans la formation
      - Diffusion des ordres de formation (leader seulement)
      - Broadcast d'urgence
    """

    def __init__(self,
                 domain_id: int = 0,
                 node_id: str = None,
                 role: str = "drone",
                 formation: str = "flying_v",
                 heartbeat_interval: float = 2.0):
        self.node_id = node_id or f"swarm_{id(self):x}"
        self.domain_id = domain_id
        self.role = role
        self.formation_type = formation
        self._heartbeat_interval = heartbeat_interval

        # PixDDS participant
        self._participant: DomainParticipant = create_participant(
            domain_id=domain_id,
            node_id=self.node_id,
        )
        self._topics: dict[str, Topic] = {}
        self._writers: dict[str, DataWriter] = {}
        self._readers: dict[str, DataReader] = {}

        # État local
        self._heartbeat = SwarmHeartbeat(
            node_id=self.node_id,
            role=self.role,
            domain_id=domain_id,
        )
        self._leader_id: Optional[str] = None
        self._leader_last_seen: float = 0.0
        self._formation_order: Optional[FormationOrder] = None
        self._members: dict[str, SwarmHeartbeat] = {}
        self._emergency_active = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callbacks utilisateur
        self.on_formation_change: Optional[Callable] = None
        self.on_emergency: Optional[Callable] = None
        self.on_leader_change: Optional[Callable] = None

    # ── Setup DDS topics ───────────────────────────────────

    def _setup_topics(self):
        for name in [HEARTBEAT_TOPIC, FORMATION_TOPIC,
                     EMERGENCY_TOPIC, LEADER_TOPIC]:
            self._topics[name] = self._participant.create_topic(name)

        # Writers
        self._writers["heartbeat"] = self._participant.create_writer(
            self._topics[HEARTBEAT_TOPIC]
        )
        self._writers["formation"] = self._participant.create_writer(
            self._topics[FORMATION_TOPIC]
        )
        self._writers["emergency"] = self._participant.create_writer(
            self._topics[EMERGENCY_TOPIC]
        )
        self._writers["leader"] = self._participant.create_writer(
            self._topics[LEADER_TOPIC]
        )

        # Readers with callbacks
        self._readers["heartbeat"] = self._participant.create_reader(
            self._topics[HEARTBEAT_TOPIC],
            callback=self._on_heartbeat,
        )
        self._readers["formation"] = self._participant.create_reader(
            self._topics[FORMATION_TOPIC],
            callback=self._on_formation,
        )
        self._readers["emergency"] = self._participant.create_reader(
            self._topics[EMERGENCY_TOPIC],
            callback=self._on_emergency,
        )
        self._readers["leader"] = self._participant.create_reader(
            self._topics[LEADER_TOPIC],
            callback=self._on_leader_msg,
        )

    # ── Callbacks DDS ──────────────────────────────────────

    def _on_heartbeat(self, data: dict, sample):
        nid = data.get("node_id")
        if nid == self.node_id:
            return
        hb = SwarmHeartbeat.from_dict(data)
        with self._lock:
            self._members[nid] = hb

    def _on_formation(self, data: dict, sample):
        if data.get("type") != "FORMATION_ORDER":
            return
        fo = FormationOrder.from_dict(data)
        with self._lock:
            self._formation_order = fo
        if self.on_formation_change:
            self.on_formation_change(fo)

    def _on_emergency(self, data: dict, sample):
        msg_type = data.get("type", "EMERGENCY")
        with self._lock:
            if msg_type == "EMERGENCY_CLEAR":
                self._emergency_active = False
            else:
                self._emergency_active = True
        if msg_type != "EMERGENCY_CLEAR":
            print(f"[PixSwarm]  URGENCE de {sample.source_node}: {data.get('msg', '')}")
        if self.on_emergency:
            self.on_emergency(data)

    def _on_leader_msg(self, data: dict, sample):
        nid = data.get("node_id")
        if nid == self.node_id:
            return
        with self._lock:
            self._leader_id = nid
            self._leader_last_seen = time.monotonic()

    # ── Boucle interne ─────────────────────────────────────

    def _loop(self):
        while self._running:
            now = time.monotonic()

            with self._lock:
                # Nettoyer les membres périmés
                stale = []
                for nid, hb in self._members.items():
                    if now - hb.timestamp > 10.0:
                        stale.append(nid)
                for nid in stale:
                    del self._members[nid]

                # Élection de leader
                if (self._leader_id is None or
                    (now - self._leader_last_seen) > LEADER_TIMEOUT):
                    self._elect_leader()

                # Calcul du slot dans la formation
                self._update_formation_slot()

            # Heartbeat
            self._publish_heartbeat()

            # Si on est leader, publier ordre de formation
            if self._is_leader:
                self._publish_formation_order()

            time.sleep(self._heartbeat_interval)

    def _publish_heartbeat(self):
        hb = self._heartbeat
        hb.timestamp = time.monotonic()
        self._writers["heartbeat"].write(hb.to_dict())

    def _publish_formation_order(self):
        members = sorted(self._members.keys())
        order = FormationOrder(
            ftype=self.formation_type,
            leader_id=self.node_id,
            members=[self.node_id] + members,
        )
        writer = self._writers.get("formation")
        if writer:
            writer.write(order.to_dict())

    def _elect_leader(self):
        """Élit le leader : d'abord par batterie, puis par ancienneté."""
        candidates = list(self._members.values())
        if not candidates:
            self._leader_id = self.node_id
            self._leader_last_seen = time.monotonic()
            return

        # Meilleure batterie, puis load_avg le plus bas
        best = max(candidates, key=lambda h: (h.battery, -h.load_avg))
        if best.battery > self._heartbeat.battery:
            self._leader_id = best.node_id
            self._leader_last_seen = best.timestamp
        else:
            self._leader_id = self.node_id
            self._leader_last_seen = time.monotonic()

        # Annoncer le leader
        writer = self._writers.get("heartbeat")
        if writer:
            writer.write({
                "type": "LEADER_ANNOUNCE",
                "node_id": self._leader_id,
                "domain_id": self.domain_id,
                "timestamp": time.monotonic(),
            })

    def _update_formation_slot(self):
        if self._leader_id is None or self._formation_order is None:
            return
        members = self._formation_order.members
        try:
            idx = members.index(self.node_id)
        except ValueError:
            idx = -1
        self._heartbeat.formation_slot = idx

    # ── API publique ───────────────────────────────────────

    @property
    def _is_leader(self) -> bool:
        return self._leader_id == self.node_id

    @property
    def is_leader(self) -> bool:
        with self._lock:
            return self._is_leader

    def start(self):
        if self._running:
            return
        self._running = True
        self._setup_topics()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        # Attendre le premier heartbeat
        time.sleep(0.1)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        self._participant.close()

    def update_heartbeat(self, battery: int = None,
                         load_avg: float = None,
                         position: tuple = None):
        if battery is not None:
            self._heartbeat.battery = battery
        if load_avg is not None:
            self._heartbeat.load_avg = load_avg
        if position is not None:
            self._heartbeat.position = position

    def broadcast_emergency(self, msg: str, level: str = "CRITICAL"):
        """Diffuser une urgence à tout l'essaim."""
        writer = self._writers.get("emergency")
        if writer:
            writer.write({
                "type": "EMERGENCY",
                "node_id": self.node_id,
                "msg": msg,
                "level": level,
                "timestamp": time.monotonic(),
            })
        self._emergency_active = True

    def clear_emergency(self):
        self._emergency_active = False
        writer = self._writers.get("emergency")
        if writer:
            writer.write({
                "type": "EMERGENCY_CLEAR",
                "node_id": self.node_id,
                "timestamp": time.monotonic(),
            })

    def set_formation(self, ftype: str):
        """Changer le type de formation (seulement si leader)."""
        if not self._is_leader:
            return False
        self.formation_type = ftype
        return True

    # ── Status ─────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            return {
                "node_id": self.node_id,
                "domain_id": self.domain_id,
                "role": self.role,
                "is_leader": self._is_leader,
                "leader_id": self._leader_id,
                "formation": self.formation_type,
                "formation_order": self._formation_order.to_dict()
                    if self._formation_order else None,
                "members": len(self._members),
                "member_list": list(self._members.keys()),
                "battery": self._heartbeat.battery,
                "load_avg": self._heartbeat.load_avg,
                "position": list(self._heartbeat.position),
                "formation_slot": self._heartbeat.formation_slot,
                "emergency": self._emergency_active,
                "running": self._running,
            }

    def get_members(self) -> list[dict]:
        with self._lock:
            return [hb.to_dict() for hb in self._members.values()]


__all__ = [
    "PixSwarm",
    "SwarmHeartbeat", "FormationOrder",
    "FormationType", "NodeRole", "NodeStatus",
    "HEARTBEAT_TOPIC", "FORMATION_TOPIC",
    "EMERGENCY_TOPIC", "LEADER_TOPIC",
]
