"""
PixHardwareMap — Routes Flask pour la visualisation 3D.
"""

import threading
from flask import jsonify

from . import PixHardwareMap


_map: PixHardwareMap = None
_map_lock = threading.Lock()


def _get_map() -> PixHardwareMap:
    global _map
    with _map_lock:
        if _map is None:
            _map = PixHardwareMap()
        return _map


def register_pixhardwaremap_routes(app):

    # On hooke aussi le routeur du PixEngineer pour partager les modules
    @app.before_request
    def _hook_engineer_modules():
        hm = _get_map()
        if hm._hardware is None:
            try:
                from ..pixengineer.routes import _get_engineer
                eng = _get_engineer()
                hm.set_modules(
                    hardware=eng._hardware,
                    predict=eng._predict,
                    maintenance_bot=eng._maintenance_bot,
                )
            except Exception:
                pass

    @app.route("/api/pixhardwaremap/topology")
    def phm_topology():
        return jsonify(_get_map().get_topology())

    @app.route("/api/pixhardwaremap/scene")
    def phm_scene():
        return jsonify(_get_map().get_scene())

    @app.route("/api/pixhardwaremap/layers")
    def phm_layers():
        return jsonify(_get_map().get_layers())

    @app.route("/api/pixhardwaremap/layers/<layer_name>/toggle", methods=["POST"])
    def phm_toggle_layer(layer_name):
        result = _get_map().toggle_layer(layer_name)
        if result is None:
            return jsonify({"error": f"unknown layer '{layer_name}'"}), 404
        return jsonify({"layer": layer_name, "visible": result})

    @app.route("/api/pixhardwaremap/inspect/<node_id>")
    def phm_inspect(node_id):
        data = _get_map().inspect_node(node_id)
        if data is None:
            return jsonify({"error": f"node '{node_id}' not found in topology"}), 404
        return jsonify(data)

    @app.route("/api/pixhardwaremap/status")
    def phm_status():
        return jsonify(_get_map().status())
