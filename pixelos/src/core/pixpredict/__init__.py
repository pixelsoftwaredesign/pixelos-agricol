"""
PixPredict — Moteur de maintenance prédictive.
Analyse les tendances des métriques matérielles (température,
vibration, courant) pour estimer la durée de vie restante (RUL)
et planifier les interventions avant la panne.
"""

import time
import math
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class ComponentPrediction:
    node_id: str
    rul_hours: float
    failure_probability: float
    primary_indicator: str
    confidence: float
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "rul_hours": round(self.rul_hours, 1),
            "failure_probability": round(self.failure_probability, 3),
            "primary_indicator": self.primary_indicator,
            "confidence": round(self.confidence, 2),
            "timestamp": self.timestamp,
            "status": "CRITICAL" if self.rul_hours < 10 else "WARN" if self.rul_hours < 50 else "OK",
        }


@dataclass
class MaintenanceTask:
    node_id: str
    task_type: str
    priority: float
    description: str
    created_at: float = 0.0
    scheduled_at: float = 0.0
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "description": self.description,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "completed": self.completed,
        }


_TEMP_BASELINE = 45.0
_CURRENT_BASELINE = 1.2
_VIBRATION_BASELINE = 0.05


class PixPredict:
    """Moteur de prédiction TinyML.

    Calcule le RUL (Remaining Useful Life) de chaque composant
    à partir de l'historique des métriques.
    """

    def __init__(self):
        self._predictions: dict[str, ComponentPrediction] = {}
        self._tasks: list[MaintenanceTask] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.on_prediction_updated: Optional[Callable] = None
        self.on_critical_prediction: Optional[Callable] = None

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def analyze(self, node_id: str, metrics_history: list[dict]) -> ComponentPrediction:
        if len(metrics_history) < 5:
            return ComponentPrediction(
                node_id=node_id, rul_hours=999.0, failure_probability=0.0,
                primary_indicator="insufficient_data", confidence=0.0,
                timestamp=time.time(),
            )

        recent = metrics_history[-50:]

        temp_avg = sum(m["temp"] for m in recent) / len(recent)
        current_avg = sum(m["current"] for m in recent) / len(recent)
        vibration_avg = sum(m["vibration"] for m in recent) / len(recent)

        temp_drift = max(0.0, (temp_avg - _TEMP_BASELINE) / _TEMP_BASELINE)
        current_drift = max(0.0, (current_avg - _CURRENT_BASELINE) / _CURRENT_BASELINE)
        vibration_drift = max(0.0, (vibration_avg - _VIBRATION_BASELINE) / _VIBRATION_BASELINE)

        if len(metrics_history) >= 20:
            older = metrics_history[-50:-20] if len(metrics_history) >= 50 else metrics_history[:len(recent)-10]
            if older:
                temp_trend = temp_avg - (sum(m["temp"] for m in older) / len(older))
                current_trend = current_avg - (sum(m["current"] for m in older) / len(older))
                vibration_trend = vibration_avg - (sum(m["vibration"] for m in older) / len(older))
            else:
                temp_trend = current_trend = vibration_trend = 0.0
        else:
            temp_trend = current_trend = vibration_trend = 0.0

        drift_scores = {
            "temperature": temp_drift + max(0.0, temp_trend * 2),
            "current": current_drift + max(0.0, current_trend * 2),
            "vibration": vibration_drift + max(0.0, vibration_trend * 5),
        }

        primary = max(drift_scores, key=drift_scores.get)
        total_drift = sum(drift_scores.values())

        failure_prob = min(1.0, total_drift / 5.0)
        confidence = min(1.0, len(metrics_history) / 200.0)

        if total_drift < 0.5:
            rul_hours = 1000.0
        elif total_drift < 1.0:
            rul_hours = 500.0
        elif total_drift < 2.0:
            rul_hours = 150.0
        elif total_drift < 3.5:
            rul_hours = 50.0
        else:
            rul_hours = max(1.0, 50.0 / total_drift)

        pred = ComponentPrediction(
            node_id=node_id,
            rul_hours=rul_hours,
            failure_probability=failure_prob,
            primary_indicator=primary,
            confidence=confidence,
            timestamp=time.time(),
        )

        with self._lock:
            self._predictions[node_id] = pred

        if self.on_prediction_updated:
            self.on_prediction_updated(pred)
        if rul_hours < 10 and self.on_critical_prediction:
            self.on_critical_prediction(pred)

        return pred

    def get_prediction(self, node_id: str) -> Optional[ComponentPrediction]:
        with self._lock:
            return self._predictions.get(node_id)

    def get_all_predictions(self) -> dict[str, ComponentPrediction]:
        with self._lock:
            return dict(self._predictions)

    def generate_task(self, pred: ComponentPrediction) -> MaintenanceTask:
        if pred.rul_hours < 10:
            task_type = "URGENT_REPLACEMENT"
            priority = 1.0
            desc = f"Remplacement urgent {pred.node_id} dans {pred.rul_hours:.0f}h"
        elif pred.rul_hours < 50:
            task_type = "SCHEDULED_MAINTENANCE"
            priority = 0.7
            desc = f"Maintenance programmée {pred.node_id} dans {pred.rul_hours:.0f}h"
        elif pred.rul_hours < 200:
            task_type = "INSPECTION"
            priority = 0.4
            desc = f"Inspection {pred.node_id} - dérive {pred.primary_indicator}"
        else:
            task_type = "MONITOR"
            priority = 0.1
            desc = f"Surveillance {pred.node_id} - {pred.primary_indicator}"

        task = MaintenanceTask(
            node_id=pred.node_id,
            task_type=task_type,
            priority=priority,
            description=desc,
            created_at=time.time(),
            scheduled_at=time.time() + max(0, pred.rul_hours * 3600 - 7200),
        )
        with self._lock:
            self._tasks.append(task)
        return task

    def get_pending_tasks(self, min_priority: float = 0.0) -> list[MaintenanceTask]:
        with self._lock:
            return [t for t in self._tasks if not t.completed and t.priority >= min_priority]

    def get_all_tasks(self) -> list[MaintenanceTask]:
        with self._lock:
            return list(self._tasks)

    def mark_completed(self, node_id: str):
        with self._lock:
            for t in self._tasks:
                if t.node_id == node_id and not t.completed:
                    t.completed = True

    def status(self) -> dict:
        with self._lock:
            pending = [t for t in self._tasks if not t.completed]
            return {
                "predictions_count": len(self._predictions),
                "critical": sum(1 for p in self._predictions.values() if p.rul_hours < 10),
                "warning": sum(1 for p in self._predictions.values() if p.rul_hours < 50),
                "tasks_pending": len(pending),
                "tasks_total": len(self._tasks),
            }

    def close(self):
        self.stop()


__all__ = [
    "PixPredict", "ComponentPrediction", "MaintenanceTask",
]
