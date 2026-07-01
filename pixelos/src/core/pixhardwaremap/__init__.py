"""
PixHardwareMap — Visualisation 3D temps réel de l'état de santé des robots.

Mappe les nœuds matériels (PixHardwareMonitor) sur un graphe 3D,
calcule les couleurs/animations selon l'état, et expose les données
de scène pour le rendu Three.js dans le dashboard PixEngineer.
"""

import time
import math
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable


# ── Constantes de topologie ────────────────────────────────

TOPOLOGY_VERSION = "1.0"

COLOR_OK = "#10b981"
COLOR_STRESS = "#f59e0b"
COLOR_CRITICAL = "#ef4444"
COLOR_FAILURE = "#7f1d1d"
COLOR_UNKNOWN = "#64748b"

NODE_RADIUS_OK = 1.0
NODE_RADIUS_STRESS = 1.2
NODE_RADIUS_CRITICAL = 1.5
NODE_RADIUS_FAILURE = 1.5

# Topologie d'un robot agricole — positions (x, y, z) normalisées
ROBOT_TOPOLOGY = {
    "CHASSIS": {
        "position": [0.0, 0.0, 0.0],
        "label": "Châssis",
        "type": "structure",
        "children": [
            "TORSO", "WHEEL_FL", "WHEEL_FR", "WHEEL_RL", "WHEEL_RR",
            "BATTERY", "CPU",
        ],
    },
    "TORSO": {
        "position": [0.0, 1.2, 0.0],
        "label": "Torse",
        "type": "structure",
        "children": [
            "ARM_LEFT_JOINT_01", "ARM_RIGHT_JOINT_01", "HEAD",
        ],
    },
    "HEAD": {
        "position": [0.0, 2.4, 0.0],
        "label": "Tête",
        "type": "structure",
        "children": ["CAMERA", "LIDAR"],
    },
    "CAMERA": {
        "position": [0.2, 2.6, 0.7],
        "label": "Caméra",
        "type": "sensor",
    },
    "LIDAR": {
        "position": [0.0, 2.8, 0.0],
        "label": "LIDAR",
        "type": "sensor",
    },
    "ARM_LEFT_JOINT_01": {
        "position": [-1.6, 1.4, 0.0],
        "label": "Bras Gauche (épaule)",
        "type": "joint",
        "children": ["ARM_LEFT_JOINT_02"],
    },
    "ARM_LEFT_JOINT_02": {
        "position": [-2.8, 0.8, 0.0],
        "label": "Bras Gauche (coude)",
        "type": "joint",
        "children": ["ARM_LEFT_GRIPPER"],
    },
    "ARM_LEFT_GRIPPER": {
        "position": [-3.6, 0.2, 0.0],
        "label": "Préhenseur Gauche",
        "type": "actuator",
    },
    "ARM_RIGHT_JOINT_01": {
        "position": [1.6, 1.4, 0.0],
        "label": "Bras Droit (épaule)",
        "type": "joint",
        "children": ["ARM_RIGHT_JOINT_02"],
    },
    "ARM_RIGHT_JOINT_02": {
        "position": [2.8, 0.8, 0.0],
        "label": "Bras Droit (coude)",
        "type": "joint",
        "children": ["ARM_RIGHT_GRIPPER"],
    },
    "ARM_RIGHT_GRIPPER": {
        "position": [3.6, 0.2, 0.0],
        "label": "Préhenseur Droit",
        "type": "actuator",
    },
    "WHEEL_FL": {
        "position": [-1.2, -0.5, 0.8],
        "label": "Roue Avant Gauche",
        "type": "wheel",
    },
    "WHEEL_FR": {
        "position": [1.2, -0.5, 0.8],
        "label": "Roue Avant Droite",
        "type": "wheel",
    },
    "WHEEL_RL": {
        "position": [-1.2, -0.5, -0.8],
        "label": "Roue Arrière Gauche",
        "type": "wheel",
    },
    "WHEEL_RR": {
        "position": [1.2, -0.5, -0.8],
        "label": "Roue Arrière Droite",
        "type": "wheel",
    },
    "BATTERY": {
        "position": [0.0, -0.3, 0.4],
        "label": "Batterie",
        "type": "power",
    },
    "CPU": {
        "position": [0.0, 0.3, 0.4],
        "label": "CPU",
        "type": "compute",
    },
    "MOTOR_01": {
        "position": [-0.8, -0.2, 0.6],
        "label": "Moteur 01",
        "type": "actuator",
    },
    "MOTOR_02": {
        "position": [0.8, -0.2, 0.6],
        "label": "Moteur 02",
        "type": "actuator",
    },
}

# Arêtes du graphe (connexions parent → enfant)
ROBOT_EDGES = []
for nid, node in ROBOT_TOPOLOGY.items():
    for child in node.get("children", []):
        if child in ROBOT_TOPOLOGY:
            ROBOT_EDGES.append((nid, child))


@dataclass
class SceneNode:
    node_id: str
    status_code: int = 0
    position: tuple = (0.0, 0.0, 0.0)
    label: str = ""
    node_type: str = "unknown"
    color: str = COLOR_OK
    radius: float = NODE_RADIUS_OK
    pulse: bool = False
    failure_count: int = 0
    last_temp: Optional[float] = None
    last_current: Optional[float] = None
    last_vibration: Optional[float] = None
    maintenance_task: Optional[str] = None
    cert_valid: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status_code": self.status_code,
            "position": list(self.position),
            "label": self.label,
            "node_type": self.node_type,
            "color": self.color,
            "radius": self.radius,
            "pulse": self.pulse,
            "failure_count": self.failure_count,
            "last_temp": self.last_temp,
            "last_current": self.last_current,
            "last_vibration": self.last_vibration,
            "maintenance_task": self.maintenance_task,
            "cert_valid": self.cert_valid,
        }


@dataclass
class LayerState:
    health: bool = True
    maintenance: bool = False
    intervention: bool = False


@dataclass
class SceneState:
    version: str = TOPOLOGY_VERSION
    generated_at: float = 0.0
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    layers: LayerState = field(default_factory=LayerState)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [{"from": s, "to": t} for s, t in self.edges],
            "layers": {
                "health": self.layers.health,
                "maintenance": self.layers.maintenance,
                "intervention": self.layers.intervention,
            },
        }


def _status_to_color(code: int) -> str:
    return [COLOR_OK, COLOR_STRESS, COLOR_CRITICAL, COLOR_FAILURE][code] if 0 <= code <= 3 else COLOR_UNKNOWN


def _status_to_radius(code: int) -> float:
    return [NODE_RADIUS_OK, NODE_RADIUS_STRESS, NODE_RADIUS_CRITICAL, NODE_RADIUS_FAILURE][code] if 0 <= code <= 3 else NODE_RADIUS_OK


def _status_pulse(code: int) -> bool:
    return code >= 2


class PixHardwareMap:
    """Moteur de la carte matérielle 3D.

    Agrège les données du PixHardwareMonitor (et optionnellement
    PixPredict / PixMaintenanceBot) pour produire une scène 3D
    prête à l'affichage par Three.js.
    """

    def __init__(self, hardware_monitor=None, predict=None, maintenance_bot=None):
        self._hardware = hardware_monitor
        self._predict = predict
        self._maintenance_bot = maintenance_bot
        self._layers = LayerState()
        self._lock = threading.Lock()
        self._cache: Optional[SceneState] = None
        self._cache_time = 0.0
        self._cache_ttl = 1.0

    def set_modules(self, hardware=None, predict=None, maintenance_bot=None):
        self._hardware = hardware
        self._predict = predict
        self._maintenance_bot = maintenance_bot

    # ── Topology ─────────────────────────────────────────

    def get_topology(self) -> dict:
        nodes = []
        edges = []
        for nid, info in ROBOT_TOPOLOGY.items():
            nodes.append({
                "id": nid,
                "position": info["position"],
                "label": info["label"],
                "type": info["type"],
            })
        for src, dst in ROBOT_EDGES:
            edges.append({"from": src, "to": dst})
        return {"version": TOPOLOGY_VERSION, "nodes": nodes, "edges": edges}

    # ── Layers ───────────────────────────────────────────

    def get_layers(self) -> dict:
        return {
            "health": self._layers.health,
            "maintenance": self._layers.maintenance,
            "intervention": self._layers.intervention,
        }

    def set_layer(self, name: str, visible: bool) -> bool:
        with self._lock:
            if hasattr(self._layers, name):
                setattr(self._layers, name, visible)
                self._invalidate_cache()
                return True
        return False

    def toggle_layer(self, name: str) -> Optional[bool]:
        with self._lock:
            if hasattr(self._layers, name):
                old = getattr(self._layers, name)
                setattr(self._layers, name, not old)
                self._invalidate_cache()
                return not old
        return None

    # ── Scene generation ─────────────────────────────────

    def _invalidate_cache(self):
        self._cache_time = 0.0

    def build_scene(self) -> SceneState:
        now = time.time()
        with self._lock:
            if self._cache and (now - self._cache_time) < self._cache_ttl:
                return self._cache

        hw_status = self._hardware.status() if self._hardware else {"nodes": {}}
        hw_nodes = hw_status.get("nodes", {})
        predictions = self._predict.get_all_predictions() if self._predict else {}
        certs = self._maintenance_bot.get_certificates() if self._maintenance_bot else []

        cert_map = {}
        for c in certs:
            cert_map[c.target_robot_id] = c

        scene_nodes = []
        for nid, info in ROBOT_TOPOLOGY.items():
            hw = hw_nodes.get(nid, {})
            status_code = hw.get("status", 0)
            fb = hw.get("last_feedback", {})
            pred = predictions.get(nid)
            cert = cert_map.get(nid)

            task_desc = None
            if pred and pred.rul_hours < 200:
                task_desc = f"RUL {pred.rul_hours}h, proba {(pred.failure_probability*100):.0f}%"

            node = SceneNode(
                node_id=nid,
                status_code=status_code,
                position=tuple(info["position"]),
                label=info["label"],
                node_type=info["type"],
                color=_status_to_color(status_code),
                radius=_status_to_radius(status_code),
                pulse=_status_pulse(status_code),
                failure_count=hw.get("failure_count", 0),
                last_temp=fb.get("temp"),
                last_current=fb.get("current"),
                last_vibration=fb.get("vibration"),
                maintenance_task=task_desc,
                cert_valid=cert.status == "VALIDATED" if cert else None,
            )
            scene_nodes.append(node)

        scene = SceneState(
            generated_at=now,
            nodes=scene_nodes,
            edges=[(s, t) for s, t in ROBOT_EDGES],
            layers=LayerState(
                health=self._layers.health,
                maintenance=self._layers.maintenance,
                intervention=self._layers.intervention,
            ),
        )

        with self._lock:
            self._cache = scene
            self._cache_time = now

        return scene

    def get_scene(self) -> dict:
        return self.build_scene().to_dict()

    def inspect_node(self, node_id: str) -> Optional[dict]:
        if node_id not in ROBOT_TOPOLOGY:
            return None
        info = dict(ROBOT_TOPOLOGY[node_id])
        info["node_id"] = node_id

        if self._hardware:
            hw = self._hardware.status().get("nodes", {}).get(node_id, {})
            info["status_code"] = hw.get("status", 0)
            info["failure_count"] = hw.get("failure_count", 0)
            info["last_feedback"] = hw.get("last_feedback")
            info["metrics_history"] = self._hardware.get_metrics_history(node_id, 50)

        if self._predict:
            pred = self._predict.get_prediction(node_id)
            if pred:
                info["prediction"] = pred.to_dict()

        if self._maintenance_bot:
            info["cert_valid"] = self._maintenance_bot.verify_certificate(node_id)

        return info

    def status(self) -> dict:
        return {
            "modules": {
                "hardware": self._hardware is not None,
                "predict": self._predict is not None,
                "maintenance_bot": self._maintenance_bot is not None,
            },
            "layers": self.get_layers(),
            "topology_nodes": len(ROBOT_TOPOLOGY),
            "topology_edges": len(ROBOT_EDGES),
            "version": TOPOLOGY_VERSION,
        }


__all__ = [
    "PixHardwareMap",
    "SceneNode", "SceneState", "LayerState",
    "ROBOT_TOPOLOGY", "ROBOT_EDGES",
    "COLOR_OK", "COLOR_STRESS", "COLOR_CRITICAL", "COLOR_FAILURE",
]
