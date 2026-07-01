"""
PixBlackBox — Routes Flask pour l'enregistreur de vol.
"""

import time
import threading
from flask import jsonify, request, Response

from . import PixBlackBox, EVENT_NAMES


_blackbox: PixBlackBox = None
_blackbox_lock = threading.Lock()


def _get_bb() -> PixBlackBox:
    global _blackbox
    with _blackbox_lock:
        if _blackbox is None:
            _blackbox = PixBlackBox()
        return _blackbox


def register_pixblackbox_routes(app):

    @app.before_request
    def _hook_blackbox_engineer():
        bb = _get_bb()
        if bb._record_count == 0:
            try:
                from ..pixengineer.routes import _get_engineer
                eng = _get_engineer()
                if eng._running:
                    bb.attach_to_engineer(eng)
            except Exception:
                pass

    @app.route("/api/pixblackbox/events")
    def pbb_events():
        event_type_name = request.args.get("type")
        event_type = None
        if event_type_name:
            rev = {v: k for k, v in EVENT_NAMES.items()}
            event_type = rev.get(event_type_name)

        start = request.args.get("start_us", type=int)
        end = request.args.get("end_us", type=int)
        limit = request.args.get("limit", 200, type=int)
        node_id = request.args.get("node_id")

        records = _get_bb().query(
            event_type=event_type,
            start_time_us=start,
            end_time_us=end,
            limit=limit,
            node_id=node_id,
        )
        return jsonify([r.to_dict() for r in records])

    @app.route("/api/pixblackbox/export")
    def pbb_export():
        event_type_name = request.args.get("type")
        event_type = None
        if event_type_name:
            rev = {v: k for k, v in EVENT_NAMES.items()}
            event_type = rev.get(event_type_name)

        start = request.args.get("start_us", type=int)
        end = request.args.get("end_us", type=int)
        node_id = request.args.get("node_id")

        csv_data = _get_bb().export_csv_string(
            event_type=event_type,
            start_time_us=start,
            end_time_us=end,
            node_id=node_id,
        )
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=pixblackbox_export.csv"},
        )

    @app.route("/api/pixblackbox/stats")
    def pbb_stats():
        return jsonify(_get_bb().stats())

    @app.route("/api/pixblackbox/clear", methods=["POST"])
    def pbb_clear():
        bb = _get_bb()
        bb.close()
        import os
        if bb._file_path.exists():
            os.remove(bb._file_path)
        bb._open_file()
        return jsonify({"status": "cleared"})
