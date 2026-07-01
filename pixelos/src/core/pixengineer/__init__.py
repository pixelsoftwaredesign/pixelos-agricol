"""
PixEngineer — Orchestrateur central de maintenance.

Agrège les données de PixHardwareMonitor, PixPredict,
PixMaintenanceBot et PixRobotCoder. Gère la boucle de décision:
surveillance → prédiction → réparation → certification.
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable

from ..pixhardware import PixHardwareMonitor
from ..pixpredict import PixPredict, MaintenanceTask
from ..pixmaintenance import PixMaintenanceBot, RepairOrder
from ..pixrobotcoder import PixRobotCoder


class EngineerMode:
    IDLE = "idle"
    MONITORING = "monitoring"
    ANALYZING = "analyzing"
    REPAIRING = "repairing"
    VERIFYING = "verifying"
    EMERGENCY = "emergency"


@dataclass
class EngineerReport:
    timestamp: float = 0.0
    total_nodes: int = 0
    healthy_nodes: int = 0
    stress_nodes: int = 0
    critical_nodes: int = 0
    failure_nodes: int = 0
    predictions_count: int = 0
    tasks_pending: int = 0
    repairs_completed: int = 0
    mode: str = EngineerMode.IDLE
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_nodes": self.total_nodes,
            "healthy_nodes": self.healthy_nodes,
            "stress_nodes": self.stress_nodes,
            "critical_nodes": self.critical_nodes,
            "failure_nodes": self.failure_nodes,
            "predictions_count": self.predictions_count,
            "tasks_pending": self.tasks_pending,
            "repairs_completed": self.repairs_completed,
            "mode": self.mode,
            "summary": self.summary,
        }


class PixEngineer:
    """Orchestrateur central de maintenance.

    Boucle principale:
      1. Lire l'état matériel (PixHardwareMonitor)
      2. Analyser les tendances (PixPredict)
      3. Planifier les réparations (PixMaintenanceBot)
      4. Générer et tester les patchs (PixRobotCoder)
      5. Émettre les certificats
    """

    def __init__(self, tick_interval: float = 5.0):
        self._hardware = None
        self._predict = None
        self._maintenance_bot = None
        self._robot_coder = None

        self._mode = EngineerMode.IDLE
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_interval = tick_interval
        self._last_report: Optional[EngineerReport] = None
        self._history: list = []

        self.on_mode_change: Optional[Callable] = None
        self.on_report: Optional[Callable] = None
        self.on_emergency: Optional[Callable] = None

    def set_modules(self, hardware=None, predict=None,
                    maintenance_bot=None, robot_coder=None):
        self._hardware = hardware
        self._predict = predict
        self._maintenance_bot = maintenance_bot
        self._robot_coder = robot_coder

    def start(self):
        self._running = True
        self._set_mode(EngineerMode.MONITORING)
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _set_mode(self, mode: str):
        with self._lock:
            old_mode = self._mode
            self._mode = mode
        if old_mode != mode and self.on_mode_change:
            self.on_mode_change(mode)

    @property
    def mode(self) -> str:
        return self._mode

    def _main_loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"[PixEngineer] Erreur tick: {e}")
            time.sleep(self._tick_interval)

    def _tick(self):
        hw = self._hardware
        pred = self._predict
        mb = self._maintenance_bot
        coder = self._robot_coder

        if not hw:
            return

        hw_status = hw.status()
        total = hw_status["total_nodes"]
        failures = hw_status["failure"]
        critical = hw_status["critical"]
        stress = hw_status["stress"]

        if failures > 0:
            self._set_mode(EngineerMode.EMERGENCY)
            if self.on_emergency:
                self.on_emergency(hw_status)
            self._handle_emergency(hw_status)
        elif critical > 0:
            self._set_mode(EngineerMode.REPAIRING)
            self._handle_critical(hw_status, pred, mb)
        elif stress > 0:
            self._set_mode(EngineerMode.ANALYZING)
            self._handle_stress(hw_status, pred, mb)
        else:
            self._set_mode(EngineerMode.MONITORING)
            self._handle_routine(hw_status, pred)

        self._generate_report(hw_status)

    def _handle_emergency(self, hw_status: dict):
        mb = self._maintenance_bot
        coder = self._robot_coder
        self._set_mode(EngineerMode.EMERGENCY)

        for nid, node in hw_status.get("nodes", {}).items():
            if node.get("status") == 3:
                order = RepairOrder(
                    node_id=nid,
                    issue_type="EMERGENCY_FAILURE",
                    priority=1.0,
                    description=f"Panne critique sur {nid}",
                    created_at=time.time(),
                )
                if mb:
                    mb.enqueue_repair(order)

    def _handle_critical(self, hw_status: dict, pred, mb):
        for nid, node in hw_status.get("nodes", {}).items():
            if node.get("status") < 2:
                continue
            metrics = self._hardware.get_metrics_history(nid, 100) if self._hardware else []
            if pred and metrics:
                p = pred.analyze(nid, metrics)
                if p.rul_hours < 50:
                    task = pred.generate_task(p)
                    order = RepairOrder(
                        node_id=nid,
                        issue_type="CRITICAL",
                        priority=0.8,
                        description=task.description,
                        created_at=time.time(),
                    )
                    if mb:
                        mb.enqueue_repair(order)

    def _handle_stress(self, hw_status: dict, pred, mb):
        for nid, node in hw_status.get("nodes", {}).items():
            if node.get("status") != 1:
                continue
            metrics = self._hardware.get_metrics_history(nid, 100) if self._hardware else []
            if pred and metrics:
                p = pred.analyze(nid, metrics)
                if p.rul_hours < 200:
                    task = pred.generate_task(p)

    def _handle_routine(self, hw_status: dict, pred):
        if not pred:
            return
        for nid in hw_status.get("nodes", {}):
            metrics = self._hardware.get_metrics_history(nid, 100) if self._hardware else []
            if metrics:
                pred.analyze(nid, metrics)

    def _generate_report(self, hw_status: dict):
        pred = self._predict
        mb = self._maintenance_bot

        report = EngineerReport(
            timestamp=time.time(),
            total_nodes=hw_status.get("total_nodes", 0),
            healthy_nodes=hw_status.get("healthy", 0),
            stress_nodes=hw_status.get("stress", 0),
            critical_nodes=hw_status.get("critical", 0),
            failure_nodes=hw_status.get("failure", 0),
            predictions_count=pred.status()["predictions_count"] if pred else 0,
            tasks_pending=mb.status()["queue_size"] if mb else 0,
            repairs_completed=mb.status()["completed"] if mb else 0,
            mode=self._mode,
            summary=self._build_summary(hw_status),
        )

        self._last_report = report
        self._history.append(report)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        if self.on_report:
            self.on_report(report)

    def _build_summary(self, hw_status: dict) -> str:
        total = hw_status.get("total_nodes", 0)
        healthy = hw_status.get("healthy", 0)
        failures = hw_status.get("failure", 0)

        if total == 0:
            return "Aucun nœud surveillé"
        if failures > 0:
            return f"{failures} panne(s) détectée(s) - Intervention en cours"
        if healthy == total:
            return f"Tout OK - {total} nœud(s) en santé"
        return f"{healthy}/{total} nœud(s) OK - Surveillance active"

    def get_report(self) -> Optional[EngineerReport]:
        return self._last_report

    def get_history(self, limit: int = 20) -> list:
        return self._history[-limit:]

    def status(self) -> dict:
        report = self._last_report
        return {
            "mode": self._mode,
            "running": self._running,
            "tick_interval": self._tick_interval,
            "modules": {
                "hardware": self._hardware is not None,
                "predict": self._predict is not None,
                "maintenance_bot": self._maintenance_bot is not None,
                "robot_coder": self._robot_coder is not None,
            },
            "last_report": report.to_dict() if report else None,
        }

    def close(self):
        self.stop()
        if self._hardware:
            self._hardware.close()
        if self._predict:
            self._predict.close()
        if self._maintenance_bot:
            self._maintenance_bot.close()


__all__ = [
    "PixEngineer", "EngineerReport", "EngineerMode",
]
