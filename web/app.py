#!/usr/bin/env python3
"""
Pixel OS – API REST unifiée.
Monte les modules : PixHAL, PixKey, PixDAO, Digital Twin, Tasks, etc.
"""

from flask import Flask, jsonify, render_template
from core.pixhal.routes import pixhal_bp
from core.pixkey.routes import pixkey_bp
from core.pixdao.routes import pixdao_bp
from core.digital_twin.routes import twin_bp as dt_bp
from core.tasks_routes import tasks_bp

app = Flask(__name__, template_folder="../pixelos/src/web/templates",
            static_folder="../pixelos/src/web/static")

app.register_blueprint(pixhal_bp)
app.register_blueprint(pixkey_bp)
app.register_blueprint(pixdao_bp)
app.register_blueprint(dt_bp)
app.register_blueprint(tasks_bp)


@app.route("/")
def index():
    return render_template("index.html", title="Pixel OS Dashboard")


@app.route("/api/status")
def api_status():
    try:
        node_id = open("/etc/pixnet/node_id").read().strip()
    except Exception:
        node_id = "unknown"
    return jsonify({
        "node_id": node_id,
        "status": "running",
        "modules": ["pixhal", "pixkey", "pixdao", "digital_twin", "tasks"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
