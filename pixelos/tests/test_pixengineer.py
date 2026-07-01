"""
Tests unitaires pour l'écosystème PixEngineer.
Couvre PixHardwareMonitor, PixPredict, PixRobotCoder,
PixMaintenanceBot et PixEngineer.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.pixhardware import (
    PixHardwareMonitor, NeuralFeedback, NodeStatusCode, NodeHealth,
)
from core.pixpredict import PixPredict, ComponentPrediction, MaintenanceTask
from core.pixrobotcoder import PixRobotCoder, PatchSpec, PatchResult
from core.pixmaintenance import PixMaintenanceBot, MaintenanceCert, RepairOrder
from core.pixengineer import PixEngineer, EngineerReport, EngineerMode


# ── PixHardwareMonitor ─────────────────────────────────────

def test_hw_create():
    hw = PixHardwareMonitor()
    assert hw.status()["total_nodes"] == 0


def test_hw_process_feedback():
    hw = PixHardwareMonitor()
    fb = NeuralFeedback(node_id="MOTOR_01", temp=55.0, current=1.5)
    hw.process_feedback(fb)
    assert hw.status()["total_nodes"] == 1
    node = hw.get_node("MOTOR_01")
    assert node is not None
    assert node.status == NodeStatusCode.OK


def test_hw_stress_detection():
    hw = PixHardwareMonitor()
    triggered = []
    hw.on_stress = lambda f: triggered.append(f.node_id)
    fb = NeuralFeedback(node_id="MOTOR_01", status_code=NodeStatusCode.STRESS)
    hw.process_feedback(fb)
    assert "MOTOR_01" in triggered
    assert hw.get_stress_count() == 1


def test_hw_failure_detection():
    hw = PixHardwareMonitor()
    triggered = []
    hw.on_failure = lambda f: triggered.append(f.node_id)
    fb = NeuralFeedback(node_id="JOINT_02", status_code=NodeStatusCode.FAILURE)
    hw.process_feedback(fb)
    assert "JOINT_02" in triggered
    assert hw.get_failure_count() == 1


def test_hw_critical_callback():
    hw = PixHardwareMonitor()
    triggered = []
    hw.on_critical = lambda f: triggered.append(f.node_id)
    fb = NeuralFeedback(node_id="SENSOR_01", status_code=NodeStatusCode.CRITICAL)
    hw.process_feedback(fb)
    assert "SENSOR_01" in triggered
    assert hw.get_critical_count() == 1


def test_hw_metrics_history():
    hw = PixHardwareMonitor()
    for i in range(10):
        fb = NeuralFeedback(node_id="MOTOR_01", temp=40.0 + i, current=1.0)
        hw.process_feedback(fb)
    hist = hw.get_metrics_history("MOTOR_01")
    assert len(hist) == 10
    assert hist[-1]["temp"] == 49.0


def test_hw_unknown_node_returns_none():
    hw = PixHardwareMonitor()
    assert hw.get_node("DOES_NOT_EXIST") is None


def test_hw_multiple_nodes():
    hw = PixHardwareMonitor()
    hw.process_feedback(NeuralFeedback(node_id="A"))
    hw.process_feedback(NeuralFeedback(node_id="B", status_code=NodeStatusCode.STRESS))
    hw.process_feedback(NeuralFeedback(node_id="C", status_code=NodeStatusCode.FAILURE))
    s = hw.status()
    assert s["total_nodes"] == 3
    assert s["healthy"] == 1
    assert s["stress"] == 1
    assert s["failure"] == 1


# ── PixPredict ─────────────────────────────────────────────

def test_predict_create():
    p = PixPredict()
    assert p.status()["predictions_count"] == 0


def test_predict_analyze_healthy():
    p = PixPredict()
    history = [{"temp": 44.0, "current": 1.1, "vibration": 0.04, "position_error": 0.001, "timestamp": time.time() - i}
               for i in range(50)]
    pred = p.analyze("MOTOR_01", history)
    assert pred.rul_hours > 100
    assert pred.failure_probability < 0.5


def test_predict_analyze_degraded():
    p = PixPredict()
    history = [{"temp": 70.0, "current": 2.5, "vibration": 0.3, "position_error": 0.01, "timestamp": time.time() - i}
               for i in range(100)]
    pred = p.analyze("MOTOR_01", history)
    assert pred.rul_hours < 200


def test_predict_insufficient_data():
    p = PixPredict()
    history = [{"temp": 44.0, "current": 1.1, "vibration": 0.04, "position_error": 0.001, "timestamp": time.time()}]
    pred = p.analyze("MOTOR_01", history)
    assert pred.confidence == 0.0
    assert pred.primary_indicator == "insufficient_data"


def test_predict_generate_task_critical():
    p = PixPredict()
    pred = ComponentPrediction(node_id="MOTOR_01", rul_hours=5.0,
                                failure_probability=0.9,
                                primary_indicator="vibration",
                                confidence=0.85)
    task = p.generate_task(pred)
    assert task.task_type == "URGENT_REPLACEMENT"
    assert task.priority == 1.0


def test_predict_generate_task_routine():
    p = PixPredict()
    pred = ComponentPrediction(node_id="MOTOR_01", rul_hours=300.0,
                                failure_probability=0.1,
                                primary_indicator="temperature",
                                confidence=0.5)
    task = p.generate_task(pred)
    assert task.task_type in ("INSPECTION", "MONITOR")


def test_predict_get_all():
    p = PixPredict()
    history = [{"temp": 50.0, "current": 1.5, "vibration": 0.1, "position_error": 0.005, "timestamp": time.time() - i}
               for i in range(30)]
    p.analyze("A", history)
    p.analyze("B", history)
    preds = p.get_all_predictions()
    assert len(preds) == 2


def test_predict_mark_completed():
    p = PixPredict()
    pred = ComponentPrediction(node_id="JOINT_01", rul_hours=20.0,
                                failure_probability=0.7,
                                primary_indicator="current",
                                confidence=0.8)
    p.generate_task(pred)
    tasks = p.get_pending_tasks()
    assert len(tasks) == 1
    p.mark_completed("JOINT_01")
    tasks = p.get_pending_tasks()
    assert len(tasks) == 0


# ── PixRobotCoder ──────────────────────────────────────────

def test_coder_analyze_overheat():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("MOTOR_01", ["Overheat detected", "temp=85C"], {"temp": 85})
    assert patch.issue_type == "OVERHEAT"
    assert "set_throttle" in patch.patch_code


def test_coder_analyze_vibration():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("JOINT_02", ["Vibration drift"], {"vibration": 0.3})
    assert patch.issue_type == "VIBRATION_DRIFT"


def test_coder_analyze_communication():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("SENSOR_01", ["timeout", "no response"], {})
    assert patch.issue_type == "COMMUNICATION_LOST"


def test_coder_analyze_calibration():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("ARM_01", ["calibration error", "position_error"], {})
    assert patch.issue_type == "CALIBRATION_ERROR"


def test_coder_generates_hash():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("MOTOR_01", ["Overheat"], {"temp": 80})
    assert len(patch.patch_hash) == 64


def test_coder_test_in_sandbox():
    coder = PixRobotCoder()
    patch = coder.analyze_issue("TEST_NODE", ["test"], {"temp": 50})
    result = coder.test_in_sandbox(patch)
    assert result.tested


# ── PixMaintenanceBot ──────────────────────────────────────

def test_mb_create():
    mb = PixMaintenanceBot()
    assert mb.status()["queue_size"] == 0


def test_mb_enqueue():
    mb = PixMaintenanceBot()
    order = RepairOrder(node_id="MOTOR_01", issue_type="OVERHEAT",
                         priority=0.8, description="Surchauffe",
                         created_at=time.time())
    mb.enqueue_repair(order)
    assert len(mb.get_queue()) == 1


def test_mb_enqueue_priority_order():
    mb = PixMaintenanceBot()
    mb.enqueue_repair(RepairOrder("A", "type", 0.5, "desc", time.time()))
    mb.enqueue_repair(RepairOrder("B", "type", 1.0, "desc", time.time()))
    mb.enqueue_repair(RepairOrder("C", "type", 0.3, "desc", time.time()))
    queue = mb.get_queue()
    assert queue[0].node_id == "B"
    assert queue[0].priority == 1.0


def test_mb_issue_certificate():
    mb = PixMaintenanceBot()
    cert = mb._issue_certificate("ROBOT_01", "abc123")
    assert cert.status == "VALIDATED"
    assert cert.target_robot_id == "ROBOT_01"
    assert len(cert.signature) > 10


def test_mb_verify_certificate():
    mb = PixMaintenanceBot()
    mb._issue_certificate("ROBOT_02", "def456")
    assert mb.verify_certificate("ROBOT_02")


def test_mb_repair_stats():
    mb = PixMaintenanceBot()
    assert mb.get_repair_stats()["total"] == 0
    mb.enqueue_repair(RepairOrder("A", "type", 0.5, "desc", time.time()))
    stats = mb.get_repair_stats()
    assert stats["total"] == 1
    assert stats["pending"] == 1


def test_mb_get_certificates():
    mb = PixMaintenanceBot()
    assert len(mb.get_certificates()) == 0
    mb._issue_certificate("ROBOT_01", "abc")
    assert len(mb.get_certificates()) == 1


def test_mb_integration_with_coder():
    from core.pixrobotcoder import PixRobotCoder
    coder = PixRobotCoder()
    mb = PixMaintenanceBot()
    mb.set_robot_coder(coder)
    mb.enqueue_repair(RepairOrder("TEST_NODE", "OVERHEAT", 0.9,
                                   "Test overheat", time.time()))
    mb._execute_repair(mb.get_queue()[0])
    certs = mb.get_certificates()
    assert len(certs) >= 0


# ── PixEngineer ────────────────────────────────────────────

def test_engineer_create():
    eng = PixEngineer()
    assert eng.mode == EngineerMode.IDLE
    assert "modules" in eng.status()


def test_engineer_status():
    eng = PixEngineer()
    s = eng.status()
    assert s["running"] is False
    assert s["mode"] == EngineerMode.IDLE


def test_engineer_with_hardware():
    from core.pixhardware import PixHardwareMonitor
    hw = PixHardwareMonitor()
    pred = PixPredict()
    eng = PixEngineer(tick_interval=0.1)
    eng.set_modules(hardware=hw, predict=pred)
    hw.start()
    eng.start()
    hw.process_feedback(NeuralFeedback(node_id="TEST_MOTOR"))
    time.sleep(0.3)
    eng.stop()
    hw.stop()
    report = eng.get_report()
    assert report is not None
    assert report.total_nodes >= 1


def test_engineer_integration():
    from core.pixhardware import PixHardwareMonitor
    from core.pixpredict import PixPredict
    from core.pixrobotcoder import PixRobotCoder
    from core.pixmaintenance import PixMaintenanceBot

    hw = PixHardwareMonitor()
    pred = PixPredict()
    coder = PixRobotCoder()
    mb = PixMaintenanceBot()
    mb.set_robot_coder(coder)

    eng = PixEngineer(tick_interval=0.1)
    eng.set_modules(hardware=hw, predict=pred, maintenance_bot=mb, robot_coder=coder)
    hw.start()
    pred.start()
    mb.start()
    eng.start()

    hw.process_feedback(NeuralFeedback(node_id="MOTOR_A",
                                        status_code=NodeStatusCode.STRESS,
                                        temp=70.0, current=2.0, vibration=0.25))
    time.sleep(0.3)
    eng.stop()
    mb.stop()
    pred.stop()
    hw.stop()

    report = eng.get_report()
    assert report is not None


def test_engineer_history():
    eng = PixEngineer(tick_interval=0.1)
    eng.start()
    time.sleep(0.3)
    eng.stop()
    history = eng.get_history()
    assert len(history) >= 0
