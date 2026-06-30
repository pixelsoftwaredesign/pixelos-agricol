from flask import Blueprint, request, jsonify, render_template
from .orchestrator_class import PixOrchestrator

orch_bp = Blueprint("orchestrator", __name__, url_prefix="/api/orchestrator")
_orch = PixOrchestrator()


def register_orchestrator_routes(app):
    app.register_blueprint(orch_bp)

    @app.route("/orchestrator")
    def orchestrator_page():
        return render_template("orchestrator.html", title="PixOrchestrator")


@orch_bp.route("/workflows")
def api_workflows():
    return jsonify(_orch.get_workflows())


@orch_bp.route("/workflow/<wf_id>")
def api_workflow(wf_id):
    w = _orch.get_workflow(wf_id)
    if not w:
        return jsonify({"error": "not found"}), 404
    return jsonify(w)


@orch_bp.route("/workflow/create", methods=["POST"])
def api_workflow_create():
    data = request.get_json(force=True) or {}
    name = data.get("name", "unnamed")
    steps = data.get("steps", [])
    return jsonify(_orch.create_workflow(name, steps))


@orch_bp.route("/workflow/<wf_id>/update", methods=["POST"])
def api_workflow_update(wf_id):
    data = request.get_json(force=True) or {}
    return jsonify(_orch.update_workflow(wf_id, data))


@orch_bp.route("/workflow/<wf_id>/delete", methods=["POST"])
def api_workflow_delete(wf_id):
    return jsonify(_orch.delete_workflow(wf_id))


@orch_bp.route("/workflow/<wf_id>/execute", methods=["POST"])
def api_workflow_execute(wf_id):
    return jsonify(_orch.execute_workflow(wf_id))


@orch_bp.route("/tasks")
def api_tasks():
    status = request.args.get("status", "")
    return jsonify(_orch.list_tasks(status))


@orch_bp.route("/task/create", methods=["POST"])
def api_task_create():
    data = request.get_json(force=True) or {}
    return jsonify(_orch.create_task(data))


@orch_bp.route("/task/<task_id>")
def api_task_get(task_id):
    t = _orch.get_task(task_id)
    if not t:
        return jsonify({"error": "not found"}), 404
    return jsonify(t)


@orch_bp.route("/task/<task_id>/execute", methods=["POST"])
def api_task_execute(task_id):
    return jsonify(_orch.execute_task(task_id))


@orch_bp.route("/task/<task_id>/cancel", methods=["POST"])
def api_task_cancel(task_id):
    return jsonify(_orch.cancel_task(task_id))


@orch_bp.route("/task/<task_id>/delete", methods=["POST"])
def api_task_delete(task_id):
    return jsonify(_orch.delete_task(task_id))


@orch_bp.route("/history")
def api_history():
    limit = request.args.get("limit", 100, type=int)
    return jsonify(_orch.get_history(limit))


@orch_bp.route("/history/clear", methods=["POST"])
def api_history_clear():
    return jsonify(_orch.clear_history())


@orch_bp.route("/stats")
def api_stats():
    return jsonify(_orch.stats())


@orch_bp.route("/module/restart/<module_name>", methods=["POST"])
def api_module_restart(module_name):
    return jsonify(_orch.restart_module(module_name))


@orch_bp.route("/modules/managed")
def api_managed_modules():
    return jsonify(_orch.get_managed_modules())


# ── Zero-Touch Join / Fleet Management ───────────────────

@orch_bp.route("/node/join", methods=["POST"])
def api_node_join():
    data = request.get_json(force=True) or {}
    return jsonify(_orch.node_join(data))


@orch_bp.route("/node/<node_id>/confirm", methods=["POST"])
def api_node_confirm(node_id):
    data = request.get_json(force=True) or {}
    return jsonify(_orch.node_confirm(node_id))


@orch_bp.route("/fleet")
def api_fleet():
    return jsonify(_orch.get_fleet())


@orch_bp.route("/node/<node_id>")
def api_node_get(node_id):
    n = _orch.get_node(node_id)
    if "error" in n:
        return jsonify(n), 404
    return jsonify(n)
