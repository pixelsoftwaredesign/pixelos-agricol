"""
PixHardware — Moniteur matériel et système nerveux.
Reçoit les feedbacks des nœuds (PixNeuralFeedback), maintient
la carte de santé et déclenche les alertes.
"""

import time
import enum
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable


class NodeStatusCode(enum.Enum):
    OK = 0
    STRESS = 1
    CRITICAL = 2
    FAILURE = 3


@dataclass
class NeuralFeedback:
    node_id: str
    status_code: NodeStatusCode = NodeStatusCode.OK
    temp: float = 25.0
    current: float = 0.0
    vibration: float = 0.0
    position_error: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status_code": self.status_code.value,
            "status_label": self.status_code.name,
            "temp": self.temp,
            "current": self.current,
            "vibration": self.vibration,
            "position_error": self.position_error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NeuralFeedback":
        return cls(
            node_id=d["node_id"],
            status_code=NodeStatusCode(d.get("status_code", 0)),
            temp=d.get("temp", 25.0),
            current=d.get("current", 0.0),
            vibration=d.get("vibration", 0.0),
            position_error=d.get("position_error", 0.0),
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class NodeHealth:
    node_id: str
    status: NodeStatusCode = NodeStatusCode.OK
    metrics_history: list = field(default_factory=list)
    last_feedback: Optional[NeuralFeedback] = None
    failure_count: int = 0
    last_failure_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "status_label": self.status.name,
            "failure_count": self.failure_count,
            "last_feedback": self.last_feedback.to_dict() if self.last_feedback else None,
            "history_count": len(self.metrics_history),
        }


FEEDBACK_HISTORY_LIMIT = 500


class PixHardwareMonitor:
    """Surveillance asynchrone des composants matériels.

    Reçoit les paquets PixNeuralFeedback, maintient la carte de santé,
    et déclenche des callbacks en cas d'anomalie.
    """

    def __init__(self):
        self._nodes: dict[str, NodeHealth] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.on_stress: Optional[Callable] = None
        self.on_critical: Optional[Callable] = None
        self.on_failure: Optional[Callable] = None
        self.on_node_offline: Optional[Callable] = None

        self._node_timeout = 5.0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def process_feedback(self, feedback: NeuralFeedback):
        with self._lock:
            if feedback.node_id not in self._nodes:
                self._nodes[feedback.node_id] = NodeHealth(node_id=feedback.node_id)

            node = self._nodes[feedback.node_id]
            node.last_feedback = feedback
            node.metrics_history.append({
                "temp": feedback.temp,
                "current": feedback.current,
                "vibration": feedback.vibration,
                "position_error": feedback.position_error,
                "timestamp": feedback.timestamp,
                "status": feedback.status_code.value,
            })
            if len(node.metrics_history) > FEEDBACK_HISTORY_LIMIT:
                node.metrics_history = node.metrics_history[-FEEDBACK_HISTORY_LIMIT:]

            old_status = node.status
            node.status = feedback.status_code

            if feedback.status_code == NodeStatusCode.FAILURE:
                node.failure_count += 1
                node.last_failure_time = time.time()

        if feedback.status_code == NodeStatusCode.STRESS and self.on_stress:
            self.on_stress(feedback)
        elif feedback.status_code == NodeStatusCode.CRITICAL and self.on_critical:
            self.on_critical(feedback)
        elif feedback.status_code == NodeStatusCode.FAILURE and self.on_failure:
            self.on_failure(feedback)

    def _check_loop(self):
        while self._running:
            time.sleep(1.0)
            now = time.time()
            with self._lock:
                for node_id, node in list(self._nodes.items()):
                    if node.last_feedback and (now - node.last_feedback.timestamp) > self._node_timeout:
                        if node.status != NodeStatusCode.FAILURE:
                            node.status = NodeStatusCode.CRITICAL
                            if self.on_node_offline:
                                self.on_node_offline(node_id)

    def get_node(self, node_id: str) -> Optional[NodeHealth]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_all_nodes(self) -> dict[str, NodeHealth]:
        with self._lock:
            return dict(self._nodes)

    def get_healthy_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes.values() if n.status == NodeStatusCode.OK)

    def get_stress_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes.values() if n.status == NodeStatusCode.STRESS)

    def get_critical_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes.values() if n.status == NodeStatusCode.CRITICAL)

    def get_failure_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes.values() if n.status == NodeStatusCode.FAILURE)

    def status(self) -> dict:
        with self._lock:
            return {
                "total_nodes": len(self._nodes),
                "healthy": self.get_healthy_count(),
                "stress": self.get_stress_count(),
                "critical": self.get_critical_count(),
                "failure": self.get_failure_count(),
                "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            }

    def get_metrics_history(self, node_id: str, limit: int = 100) -> list:
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return []
            return node.metrics_history[-limit:]

    def close(self):
        self.stop()


__all__ = [
    "PixHardwareMonitor", "NodeHealth", "NeuralFeedback", "NodeStatusCode",
]
