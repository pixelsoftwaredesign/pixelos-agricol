"""
Flask routes for PixVision — Scanner IoT + Détection Vision + Registry.
"""

from flask import Blueprint, request, jsonify, render_template
from .scanner import scanner
from .detector import detector, env_map
from .registry import registry
from .oui_db import lookup_oui

pixvision_bp = Blueprint("pixvision", __name__, url_prefix="/api/pixvision")


def register_pixvision_routes(app):
    app.register_blueprint(pixvision_bp)

    @app.route("/pixvision")
    def pixvision_page():
        return render_template("pixvision.html", title="PixVision — Scanner IoT & Vision")


# ═══════════════════════════════════════════════════════════
# Scanner IoT
# ═══════════════════════════════════════════════════════════

@pixvision_bp.route("/scan", methods=["POST"])
def api_pixvision_scan():
    data = request.get_json(silent=True) or {}
    deep = data.get("deep", False)
    result = scanner.scan(deep=deep)
    # Auto-enregistrer les devices réseau dans le registre
    if result.get("total_devices", 0) > 0:
        for dev in scanner.get_devices():
            registry.register_network(
                mac=dev["mac"], ip=dev["ip"],
                manufacturer=dev.get("manufacturer", ""),
                device_type=dev.get("device_type", "inconnu"),
                rssi=dev.get("rssi", -100),
            )
    return jsonify(result)


@pixvision_bp.route("/devices")
def api_pixvision_devices():
    status = request.args.get("status")
    devices = scanner.get_devices(status=status)
    return jsonify({"count": len(devices), "devices": devices})


@pixvision_bp.route("/devices/<mac>")
def api_pixvision_device(mac):
    dev = scanner.get_device(mac)
    if not dev:
        return jsonify({"error": "not_found"}), 404
    return jsonify(dev)


@pixvision_bp.route("/devices/<mac>/identify", methods=["POST"])
def api_pixvision_identify(mac):
    data = request.get_json(silent=True) or {}
    result = scanner.identify_device(
        mac,
        device_type=data.get("device_type", "inconnu"),
        manufacturer=data.get("manufacturer", ""),
    )
    return jsonify(result)


@pixvision_bp.route("/devices/<mac>", methods=["DELETE"])
def api_pixvision_remove(mac):
    result = scanner.remove_device(mac)
    return jsonify(result)


@pixvision_bp.route("/oui/<mac>")
def api_pixvision_oui(mac):
    return jsonify(lookup_oui(mac.upper()))


@pixvision_bp.route("/stats")
def api_pixvision_stats():
    return jsonify(scanner.stats())


# ═══════════════════════════════════════════════════════════
# Détection Vision (PixDetector)
# ═══════════════════════════════════════════════════════════

@pixvision_bp.route("/detect", methods=["POST"])
def api_pixvision_detect():
    """Exécuter une détection et enregistrer les objets dans le registre."""
    actions = detector.process_frame()
    status = detector.status()

    # Auto-enregistrer les détections physiques
    for action in actions:
        registry.register_physical(
            class_name=action["class"],
            confidence=action["confidence"],
            pos_x=0.0,  # TODO: GPS coords from SLAM
            pos_y=0.0,
        )

    return jsonify({
        "actions": actions,
        "status": status,
    })


@pixvision_bp.route("/detector/status")
def api_pixvision_detector_status():
    return jsonify(detector.status())


@pixvision_bp.route("/detector/start", methods=["POST"])
def api_pixvision_detector_start():
    detector.start()
    return jsonify({"running": True})


@pixvision_bp.route("/detector/stop", methods=["POST"])
def api_pixvision_detector_stop():
    detector.stop()
    return jsonify({"running": False})


@pixvision_bp.route("/detector/emergency", methods=["POST"])
def api_pixvision_detector_emergency():
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "manual")
    detector.emergency_stop(reason)
    return jsonify({"action": "STOP_IMMEDIAT", "reason": reason})


@pixvision_bp.route("/detector/log")
def api_pixvision_detector_log():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"events": detector.reactor.get_log(limit=limit)})


@pixvision_bp.route("/detector/log/clear", methods=["POST"])
def api_pixvision_detector_log_clear():
    detector.reactor.clear_log()
    return jsonify({"cleared": True})


# ═══════════════════════════════════════════════════════════
# Environment Map
# ═══════════════════════════════════════════════════════════

@pixvision_bp.route("/map")
def api_pixvision_map():
    class_name = request.args.get("class")
    obstacles = env_map.get_obstacles(class_name=class_name)
    stats = env_map.stats()
    return jsonify({"obstacles": obstacles, "stats": stats})


@pixvision_bp.route("/map/clear", methods=["POST"])
def api_pixvision_map_clear():
    env_map.clear()
    return jsonify({"cleared": True})


@pixvision_bp.route("/map/check-collision", methods=["POST"])
def api_pixvision_map_collision():
    data = request.get_json(silent=True) or {}
    x = data.get("x", 0.0)
    y = data.get("y", 0.0)
    robot_radius = data.get("robot_radius", 0.5)
    obs = env_map.check_collision(x, y, robot_radius)
    return jsonify({
        "collision": obs is not None,
        "obstacle": obs.to_dict() if obs else None,
    })


# ═══════════════════════════════════════════════════════════
# Object Registry (Fusion)
# ═══════════════════════════════════════════════════════════

@pixvision_bp.route("/registry")
def api_pixvision_registry():
    device_type = request.args.get("type")
    status = request.args.get("status")
    objects = registry.list_objects(device_type=device_type, status=status)
    stats = registry.stats()
    return jsonify({"objects": objects, "stats": stats})


@pixvision_bp.route("/registry/<obj_id>")
def api_pixvision_registry_get(obj_id):
    obj = registry.get_object(obj_id)
    if not obj:
        return jsonify({"error": "not_found"}), 404
    return jsonify(obj)


@pixvision_bp.route("/registry/<obj_id>/status", methods=["POST"])
def api_pixvision_registry_status(obj_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status", "unknown")
    result = registry.set_status(obj_id, status)
    return jsonify(result)


@pixvision_bp.route("/registry/<obj_id>", methods=["DELETE"])
def api_pixvision_registry_delete(obj_id):
    result = registry.delete_object(obj_id)
    return jsonify(result)


@pixvision_bp.route("/registry/auto-fuse", methods=["POST"])
def api_pixvision_registry_autofuse():
    count = registry.auto_fuse()
    return jsonify({"fused": count})


# ═══════════════════════════════════════════════════════════
# PixIPC Bus
# ═══════════════════════════════════════════════════════════

@pixvision_bp.route("/pixipc/messages")
def api_pixipc_messages():
    from core.pixipc import bus
    msg_type = request.args.get("type")
    limit = request.args.get("limit", 50, type=int)
    msgs = bus.get_log(msg_type=msg_type, limit=limit)
    return jsonify({"messages": msgs})


@pixvision_bp.route("/pixipc/stats")
def api_pixipc_stats():
    from core.pixipc import bus
    return jsonify(bus.stats())
