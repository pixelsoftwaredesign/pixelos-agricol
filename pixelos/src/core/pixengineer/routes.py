"""
PixEngineer — Routes Flask pour le dashboard d'orchestration.
"""

import time
import threading
from flask import jsonify, request, render_template
from ..pixhardware import PixHardwareMonitor, NeuralFeedback, NodeStatusCode
from ..pixpredict import PixPredict, MaintenanceTask
from ..pixmaintenance import PixMaintenanceBot, RepairOrder
from ..pixrobotcoder import PixRobotCoder
from . import PixEngineer


_engineer: PixEngineer = None
_engineer_lock = threading.Lock()


def _get_engineer() -> PixEngineer:
    global _engineer
    with _engineer_lock:
        if _engineer is None:
            hw = PixHardwareMonitor()
            pred = PixPredict()
            coder = PixRobotCoder()
            mb = PixMaintenanceBot()
            mb.set_robot_coder(coder)

            eng = PixEngineer()
            eng.set_modules(hardware=hw, predict=pred,
                           maintenance_bot=mb, robot_coder=coder)
            hw.start()
            pred.start()
            mb.start()
            eng.start()
            _engineer = eng
        return _engineer


def register_pixengineer_routes(app):
    @app.route("/pixengineer/status")
    def pixengineer_status():
        return jsonify(_get_engineer().status())

    @app.route("/pixengineer/report")
    def pixengineer_report():
        eng = _get_engineer()
        report = eng.get_report()
        return jsonify(report.to_dict() if report else {})

    @app.route("/pixengineer/history")
    def pixengineer_history():
        limit = request.args.get("limit", 20, type=int)
        history = _get_engineer().get_history(limit)
        return jsonify([r.to_dict() for r in history])

    @app.route("/pixengineer/hardware")
    def pixengineer_hardware():
        eng = _get_engineer()
        if eng._hardware:
            return jsonify(eng._hardware.status())
        return jsonify({"error": "hardware module not loaded"}), 503

    @app.route("/pixengineer/hardware/<node_id>/history")
    def pixengineer_hardware_node_history(node_id):
        eng = _get_engineer()
        if eng._hardware:
            limit = request.args.get("limit", 100, type=int)
            return jsonify(eng._hardware.get_metrics_history(node_id, limit))
        return jsonify({"error": "hardware module not loaded"}), 503

    @app.route("/pixengineer/feedback", methods=["POST"])
    def pixengineer_feedback():
        body = request.get_json(force=True)
        eng = _get_engineer()
        if eng._hardware:
            fb = NeuralFeedback.from_dict(body)
            eng._hardware.process_feedback(fb)
            return jsonify({"status": "processed", "node": fb.node_id})
        return jsonify({"error": "hardware module not loaded"}), 503

    @app.route("/pixengineer/predictions")
    def pixengineer_predictions():
        eng = _get_engineer()
        if eng._predict:
            preds = eng._predict.get_all_predictions()
            return jsonify({nid: p.to_dict() for nid, p in preds.items()})
        return jsonify({"error": "predict module not loaded"}), 503

    @app.route("/pixengineer/tasks")
    def pixengineer_tasks():
        eng = _get_engineer()
        if eng._maintenance_bot:
            min_prio = request.args.get("min_priority", 0.0, type=float)
            tasks = eng._maintenance_bot.get_queue()
            tasks = [t for t in tasks if t.priority >= min_prio]
            return jsonify([t.to_dict() for t in tasks])
        return jsonify({"error": "maintenance_bot module not loaded"}), 503

    @app.route("/pixengineer/certificates")
    def pixengineer_certificates():
        eng = _get_engineer()
        if eng._maintenance_bot:
            certs = eng._maintenance_bot.get_certificates()
            return jsonify([c.to_dict() for c in certs])
        return jsonify({"error": "maintenance_bot module not loaded"}), 503

    @app.route("/pixengineer/verify/<node_id>")
    def pixengineer_verify(node_id):
        eng = _get_engineer()
        if eng._maintenance_bot:
            ok = eng._maintenance_bot.verify_certificate(node_id)
            return jsonify({"node_id": node_id, "certified": ok})
        return jsonify({"error": "maintenance_bot module not loaded"}), 503

    @app.route("/pixengineer/repair", methods=["POST"])
    def pixengineer_repair():
        body = request.get_json(force=True)
        eng = _get_engineer()
        if eng._maintenance_bot:
            order = RepairOrder(
                node_id=body["node_id"],
                issue_type=body.get("issue_type", "MANUAL"),
                priority=body.get("priority", 0.5),
                description=body.get("description", "Réparation manuelle"),
                created_at=time.time(),
            )
            eng._maintenance_bot.enqueue_repair(order)
            return jsonify({"status": "enqueued", "node": order.node_id})
        return jsonify({"error": "maintenance_bot module not loaded"}), 503

    @app.route("/pixengineer/simulate", methods=["POST"])
    def pixengineer_simulate():
        body = request.get_json(force=True)
        eng = _get_engineer()
        if eng._hardware:
            fb = NeuralFeedback(
                node_id=body.get("node_id", "SIM_MOTOR_01"),
                status_code=NodeStatusCode(body.get("status_code", 1)),
                temp=body.get("temp", 55.0),
                current=body.get("current", 1.5),
                vibration=body.get("vibration", 0.12),
                position_error=body.get("position_error", 0.01),
            )
            eng._hardware.process_feedback(fb)
            return jsonify({"status": "simulated", "feedback": fb.to_dict()})
        return jsonify({"error": "hardware module not loaded"}), 503

    @app.route("/pixengineer/dashboard")
    def pixengineer_dashboard():
        return render_template("pixengineer.html")
