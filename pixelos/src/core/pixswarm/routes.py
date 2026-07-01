"""
PixSwarm — Routes Flask pour le dashboard swarm.
"""

import threading
from flask import jsonify, request, render_template
from . import PixSwarm

# Singleton swarm (1 par processus)
_swarm: PixSwarm = None
_swarm_lock = threading.Lock()


def _get_swarm() -> PixSwarm:
    global _swarm
    with _swarm_lock:
        if _swarm is None:
            _swarm = PixSwarm(domain_id=0, node_id="swarm_gateway",
                              role="gateway", formation="flying_v")
            _swarm.start()
        return _swarm


def register_pixswarm_routes(app):
    @app.route("/pixswarm/status")
    def pixswarm_status():
        return jsonify(_get_swarm().status())

    @app.route("/pixswarm/start", methods=["POST"])
    def pixswarm_start():
        body = request.get_json(silent=True) or {}
        s = _get_swarm()
        if body.get("formation"):
            s.set_formation(body["formation"])
        return jsonify({"status": "running", "node": s.node_id})

    @app.route("/pixswarm/stop", methods=["POST"])
    def pixswarm_stop():
        s = _get_swarm()
        s.stop()
        return jsonify({"status": "stopped"})

    @app.route("/pixswarm/members")
    def pixswarm_members():
        s = _get_swarm()
        return jsonify({
            "count": len(s._members),
            "members": s.get_members(),
        })

    @app.route("/pixswarm/heartbeat", methods=["POST"])
    def pixswarm_heartbeat():
        body = request.get_json(force=True)
        s = _get_swarm()
        s.update_heartbeat(
            battery=body.get("battery"),
            load_avg=body.get("load_avg"),
            position=tuple(body.get("position", [])),
        )
        return jsonify({"status": "updated"})

    @app.route("/pixswarm/emergency", methods=["POST"])
    def pixswarm_emergency():
        body = request.get_json(force=True)
        s = _get_swarm()
        s.broadcast_emergency(
            msg=body.get("msg", "No details"),
            level=body.get("level", "CRITICAL"),
        )
        return jsonify({"status": "emergency_broadcast"})

    @app.route("/pixswarm/emergency/clear", methods=["POST"])
    def pixswarm_emergency_clear():
        s = _get_swarm()
        s.clear_emergency()
        return jsonify({"status": "emergency_cleared"})

    @app.route("/pixswarm/formation", methods=["POST"])
    def pixswarm_formation():
        body = request.get_json(force=True)
        ftype = body.get("formation", "flying_v")
        s = _get_swarm()
        ok = s.set_formation(ftype)
        return jsonify({
            "status": "ok" if ok else "not_leader",
            "formation": ftype,
            "is_leader": s.is_leader,
        })

    @app.route("/pixswarm/dashboard")
    def pixswarm_dashboard():
        return render_template("pixswarm.html")
