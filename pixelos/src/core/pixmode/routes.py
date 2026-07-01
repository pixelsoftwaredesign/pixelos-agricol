"""
PixMode — Routes Flask pour le dashboard mode manager.
"""

import time
import threading
from flask import jsonify, request, render_template
from . import PixModeManager, OperatorAuth, ManualCommand, SafetyStatus


_mode_manager: PixModeManager = None
_mm_lock = threading.Lock()


def _get_mm() -> PixModeManager:
    global _mode_manager
    with _mm_lock:
        if _mode_manager is None:
            _mode_manager = PixModeManager(deadman_timeout=2.0)
        return _mode_manager


def register_pixmode_routes(app):
    @app.route("/pixmode/status")
    def pixmode_status():
        return jsonify(_get_mm().status())

    @app.route("/pixmode/history")
    def pixmode_history():
        limit = request.args.get("limit", 20, type=int)
        return jsonify(_get_mm().history(limit))

    @app.route("/pixmode/mode", methods=["POST"])
    def pixmode_set_mode():
        body = request.get_json(force=True)
        target = body.get("mode", "auto")
        operator_id = body.get("operator_id")
        token = body.get("token")
        reason = body.get("reason", "")
        auth = None
        if operator_id and token:
            auth = OperatorAuth(
                operator_id=operator_id,
                role=body.get("role", "technician"),
                token=token,
                authenticated_at=time.monotonic(),
                expires_at=time.monotonic() + 3600,
            )
        ok, msg = _get_mm().request_mode(target, auth=auth, reason=reason)
        return jsonify({"status": "ok" if ok else "error", "message": msg})

    @app.route("/pixmode/command", methods=["POST"])
    def pixmode_command():
        body = request.get_json(force=True)
        cmd = ManualCommand(
            linear_vel=body.get("linear_vel", 0.0),
            angular_vel=body.get("angular_vel", 0.0),
        )
        accepted, filtered, msg = _get_mm().send_manual_command(cmd)
        return jsonify({
            "accepted": accepted,
            "command": filtered.to_dict(),
            "message": msg,
        })

    @app.route("/pixmode/deadman/kick", methods=["POST"])
    def pixmode_deadman_kick():
        _get_mm().deadman_kick()
        return jsonify({"status": "ok"})

    @app.route("/pixmode/safety", methods=["POST"])
    def pixmode_safety_update():
        body = request.get_json(force=True)
        status = SafetyStatus(
            obstacle_ahead=body.get("obstacle_ahead", False),
            obstacle_distance=body.get("obstacle_distance", 999.0),
            human_detected=body.get("human_detected", False),
            battery_critical=body.get("battery_critical", False),
            tilt_angle=body.get("tilt_angle", 0.0),
            all_clear=not (body.get("obstacle_ahead", False) or body.get("human_detected", False)),
        )
        _get_mm().safety.update_sensors(status)
        return jsonify({"status": "updated"})

    @app.route("/pixmode/selector", methods=["POST"])
    def pixmode_selector():
        body = request.get_json(force=True)
        position = body.get("position", "AUTO")
        ok, msg = _get_mm().physical_selector(position)
        return jsonify({"status": "ok" if ok else "error", "message": msg})

    @app.route("/pixmode/dashboard")
    def pixmode_dashboard():
        return render_template("pixmode.html")
