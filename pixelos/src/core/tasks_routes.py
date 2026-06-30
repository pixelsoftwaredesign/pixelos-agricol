from flask import Blueprint, request, jsonify

from .tasks import TaskManager

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")
_tm = TaskManager()


@tasks_bp.route("")
def api_tasks_list():
    status = request.args.get("status")
    if status:
        return jsonify([t for t in _tm.all() if t.get("statut") == status])
    return jsonify(_tm.all())


@tasks_bp.route("/<task_id>")
def api_task_get(task_id):
    for t in _tm.all():
        if t["id"] == task_id:
            return jsonify(t)
    return jsonify({"error": "not found"}), 404


@tasks_bp.route("", methods=["POST"])
def api_task_create():
    data = request.get_json(force=True) or {}
    if not data.get("title"):
        return jsonify({"error": "title required"}), 400
    return jsonify(_tm.create(
        title=data["title"],
        description=data.get("description", ""),
        categorie=data.get("categorie", "autre"),
        priorite=data.get("priorite", "medium"),
        zone=data.get("zone", ""),
        plante=data.get("plante", ""),
        echeance=data.get("echeance", ""),
        assignee=data.get("assignee", ""),
    ))


@tasks_bp.route("/<task_id>", methods=["PUT", "PATCH"])
def api_task_update(task_id):
    data = request.get_json(force=True) or {}
    return jsonify(_tm.update(task_id, **data))


@tasks_bp.route("/<task_id>/status", methods=["POST"])
def api_task_status(task_id):
    data = request.get_json(force=True) or {}
    status = data.get("status", "")
    if status not in _tm.STATUSES:
        return jsonify({"error": f"invalid status: {status}"}), 400
    return jsonify(_tm.update(task_id, statut=status))


@tasks_bp.route("/stats")
def api_tasks_stats():
    all_t = _tm.all()
    return jsonify({
        "total": len(all_t),
        "by_status": {s: sum(1 for t in all_t if t.get("statut") == s) for s in _tm.STATUSES},
        "by_priority": {p: sum(1 for t in all_t if t.get("priorite") == p) for p in _tm.PRIORITIES},
        "overdue": len(_tm.alerts()),
    })


@tasks_bp.route("/alerts")
def api_tasks_alerts():
    return jsonify(_tm.alerts())
