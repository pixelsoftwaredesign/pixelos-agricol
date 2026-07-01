"""
PixPowerManager — Routes Flask pour le power management.
"""

import time
import threading
from flask import jsonify, request

from . import PixPowerManager, RobotPowerState


_manager: PixPowerManager = None
_manager_lock = threading.Lock()


def _get_manager() -> PixPowerManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = PixPowerManager()
            _manager.start()
        return _manager


def register_pixpowermanager_routes(app):
    @app.route("/api/pixpower/summary")
    def pixpower_summary():
        return jsonify(_get_manager().summary())

    @app.route("/api/pixpower/robots")
    def pixpower_robots():
        return jsonify(_get_manager().list_robots())

    @app.route("/api/pixpower/robot/<robot_id>")
    def pixpower_robot(robot_id):
        mgr = _get_manager()
        robot = mgr.get_robot(robot_id)
        if not robot:
            return jsonify({"error": "robot not found"}), 404
        return jsonify(robot.to_dict())

    @app.route("/api/pixpower/robot", methods=["POST"])
    def pixpower_robot_register():
        body = request.get_json(force=True)
        mgr = _get_manager()
        entry = mgr.register_robot(
            robot_id=body["robot_id"],
            nominal_watts=body.get("nominal_watts", 100.0),
            battery_capacity_wh=body.get("battery_capacity_wh", 500.0),
        )
        return jsonify(entry.to_dict()), 201

    @app.route("/api/pixpower/robot/<robot_id>", methods=["DELETE"])
    def pixpower_robot_unregister(robot_id):
        mgr = _get_manager()
        if mgr.unregister_robot(robot_id):
            return jsonify({"status": "removed"})
        return jsonify({"error": "robot not found"}), 404

    @app.route("/api/pixpower/robot/<robot_id>/state", methods=["PUT"])
    def pixpower_robot_state(robot_id):
        body = request.get_json(force=True)
        state_str = body.get("state", "idle")
        state_map = {
            "active": RobotPowerState.ACTIVE,
            "idle": RobotPowerState.IDLE,
            "charging": RobotPowerState.CHARGING,
            "sleep": RobotPowerState.SLEEP,
            "docked": RobotPowerState.DOCKED,
        }
        state = state_map.get(state_str)
        if state is None:
            return jsonify({"error": f"invalid state: {state_str}"}), 400
        mgr = _get_manager()
        if mgr.set_state(robot_id, state):
            return jsonify({"status": "ok", "state": state_str})
        return jsonify({"error": "robot not found"}), 404

    @app.route("/api/pixpower/robot/<robot_id>/soc", methods=["PUT"])
    def pixpower_robot_soc(robot_id):
        body = request.get_json(force=True)
        soc = body.get("soc_pct", 100.0)
        mgr = _get_manager()
        if mgr.set_soc(robot_id, soc):
            return jsonify({"status": "ok", "soc_pct": soc})
        return jsonify({"error": "robot not found"}), 404

    @app.route("/api/pixpower/budget")
    def pixpower_budget():
        return jsonify(_get_manager().get_budget().to_dict())

    @app.route("/api/pixpower/inputs", methods=["PUT"])
    def pixpower_inputs():
        body = request.get_json(force=True)
        mgr = _get_manager()
        mgr.set_power_inputs(
            solar_watts=body.get("solar_watts", 0.0),
            grid_watts=body.get("grid_watts", 0.0),
            battery_soc_pct=body.get("battery_soc_pct", 80.0),
            battery_storage_wh=body.get("battery_storage_wh", 5000.0),
        )
        return jsonify({"status": "ok"})

    @app.route("/api/pixpower/charge", methods=["POST"])
    def pixpower_schedule_charge():
        body = request.get_json(force=True)
        mgr = _get_manager()
        sched = mgr.schedule_charge(
            robot_id=body["robot_id"],
            delay_seconds=body.get("delay_seconds", 0.0),
            duration_seconds=body.get("duration_seconds", 1800.0),
            reason=body.get("reason", "scheduled"),
        )
        return jsonify(sched.to_dict()), 201

    @app.route("/api/pixpower/charge")
    def pixpower_charge_schedule():
        return jsonify(_get_manager().list_charge_schedule())

    @app.route("/api/pixpower/health")
    def pixpower_health():
        return jsonify(_get_manager().list_health())

    @app.route("/api/pixpower/health/<robot_id>")
    def pixpower_health_robot(robot_id):
        mgr = _get_manager()
        health = mgr.get_health(robot_id)
        if not health:
            return jsonify({"error": "robot not found"}), 404
        return jsonify(health.to_dict())

    @app.route("/api/pixpower/history")
    def pixpower_history():
        limit = request.args.get("limit", 50, type=int)
        return jsonify(_get_manager().get_history(limit))
