#!/usr/bin/env python3
"""
PixelOS Web - Interface d'administration web.
Dashboard unifié pour gérer l'infrastructure agricole.
"""

import os
import json
from pathlib import Path
from datetime import datetime

try:
    from flask import Flask, render_template, jsonify, request
except ImportError:
    # Mode dégradé sans Flask
    app = None
    print("⚠️  Flask non installé: 'pip install pixelos[web]'")
    HAS_FLASK = False
else:
    HAS_FLASK = True

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import PixelOSConfig
from core.mqtt import PixelOSMQTT


if HAS_FLASK:
    app = Flask(__name__)
    config = PixelOSConfig()
    mqtt = PixelOSMQTT()

    @app.route("/")
    def index():
        return render_template("index.html", title="PixelOS - AgriCol")

    @app.route("/plantes")
    def plantes_page():
        return render_template("plantes.html", title="Base Plantes")

    @app.route("/services")
    def services_page():
        return render_template("services.html", title="Services")

    @app.route("/streamlit")
    def streamlit_page():
        return render_template("streamlit.html", title="Dashboard Streamlit")

    @app.route("/api/status")
    def api_status():
        """État complet du système en JSON."""
        nodes_online = []
        for n in config.nodes.values():
            nodes_online.append({
                "id": n["id"],
                "type": n["type"],
                "location": n.get("location", ""),
                "addr": n["addr"],
                "online": True,
                "icon": {
                    "capteur_sol": "🌱", "vanne": "💧", "meteo": "🌤️",
                    "debitmetre": "📊", "pir": "🚨", "pompe": "⚡",
                    "gateway": "📡",
                }.get(n["type"], "📡"),
            })

        return jsonify({
            "instance": config.get("instance_name", "ferme"),
            "time": datetime.now().isoformat(),
            "version": "2.0.0",
            "mqtt": mqtt.connected if hasattr(mqtt, 'connected') else False,
            "nodes": nodes_online,
            "nodes_online": len(nodes_online),
            "nodes_total": len(config.nodes),
        })

    @app.route("/api/nodes")
    def api_nodes():
        return jsonify(list(config.nodes.values()))

    @app.route("/api/node/<node_id>")
    def api_node(node_id: str):
        n = config.get_node(node_id)
        if not n:
            return jsonify({"error": "Node not found"}), 404
        return jsonify(n)

    @app.route("/api/alerts")
    def api_alerts():
        return jsonify(config.alerts)

    @app.route("/api/irrigation")
    def api_irrigation():
        zones = []
        for n in config.get_nodes_by_type("capteur_sol"):
            zones.append({
                "id": n["id"],
                "location": n.get("location", ""),
                "seuil": n.get("irrigation", {}).get("seuil_secheresse"),
                "hysteresis": n.get("irrigation", {}).get("hysteresis"),
                "valve": n.get("irrigation", {}).get("valve_addr"),
            })
        return jsonify({
            "auto_mode": config.get("irrigation.auto_mode", True),
            "global_hysteresis": config.get("irrigation.global_hysteresis", 5.0),
            "rain_block": config.get("irrigation.rain_block_threshold", 2.0),
            "zones": zones,
        })

    @app.route("/api/command", methods=["POST"])
    def api_command():
        """Envoyer une commande à un nœud."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        node_id = data.get("node")
        command = data.get("command")

        topic = f"agricol/commande/{node_id}"
        mqtt.publish(topic, {"cmd": command})
        return jsonify({"status": "sent", "topic": topic, "command": command})

    @app.route("/api/zones")
    def api_zones():
        """Liste des zones."""
        from core.provisioning import ZoneManager
        zm = ZoneManager()
        return jsonify(zm.list_zones())

    @app.route("/api/scan", methods=["POST"])
    def api_scan():
        """Lance un scan Wi-Fi/BLE/RS485."""
        from core.discovery import AggregateScanner
        from core.provisioning import ZoneManager

        timeout = request.get_json().get("timeout", 15) if request.is_json else 15
        auto_register = request.get_json().get("auto_register", False) if request.is_json else False
        zone = request.get_json().get("zone", "Auto-détecté") if request.is_json else "Auto-détecté"

        scanner = AggregateScanner()
        results = scanner.scan_all(timeout=timeout)

        zm = ZoneManager()
        new_nodes = zm.detect_new(results["total"])

        registered = []
        if auto_register and new_nodes:
            res = zm.register_batch(new_nodes, zone)
            registered = res["registered"]

        return jsonify({
            "wifi": results["wifi"],
            "ble": results["ble"],
            "rs485": results["rs485"],
            "total": results["total"],
            "new": new_nodes,
            "registered": registered,
            "count": {
                "wifi": len(results["wifi"]),
                "ble": len(results["ble"]),
                "rs485": len(results["rs485"]),
                "total": len(results["total"]),
                "new": len(new_nodes),
                "registered": len(registered),
            }
        })

    @app.route("/api/zone/register", methods=["POST"])
    def api_zone_register():
        """Enregistre un nœud découvert dans une zone."""
        from core.provisioning import ZoneManager

        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        zm = ZoneManager()
        node_def = {
            "id": data["id"],
            "addr": data.get("addr", 0),
            "type": data.get("type", "capteur_sol"),
            "location": data.get("location", "Auto-détecté"),
            "communication": data.get("communication", "wifi"),
            "protocol": data.get("protocol", "auto"),
            "sensors": data.get("sensors", {}),
        }
        ok = zm.register(node_def, data.get("location"))
        return jsonify({"status": "ok" if ok else "exists", "node": node_def})

    @app.route("/api/predict/train", methods=["POST"])
    def api_predict_train():
        from core.predictor import PredictorEngine
        data = request.get_json() or {}
        engine = PredictorEngine()
        result = engine.train(days=data.get("days", 30),
                              zone=data.get("zone", "sol_serre"))
        return jsonify(result)

    @app.route("/api/predict/now")
    def api_predict_now():
        from core.predictor import PredictorEngine
        engine = PredictorEngine()
        data = {
            "humidite_sol": request.args.get("humidity", 45, type=float),
            "temperature": request.args.get("temp", 20, type=float),
            "humidite": request.args.get("hum", 50, type=float),
            "pression": request.args.get("pression", 1013, type=float),
        }
        result = engine.predict(data)
        return jsonify(result)

    @app.route("/api/predict/stats")
    def api_predict_stats():
        from core.predictor import PredictorEngine
        engine = PredictorEngine()
        return jsonify(engine.stats())

    @app.route("/api/predict/anomalies", methods=["POST"])
    def api_predict_anomalies():
        from core.predictor import PredictorEngine
        engine = PredictorEngine()
        data = request.get_json() or {}
        anomalies = engine.detect_anomalies(data)
        return jsonify(anomalies)

    @app.route("/api/plantes")
    def api_plantes_list():
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        cat = request.args.get("categorie")
        cycle = request.args.get("cycle")
        rows = db.list_plantes(cat, cycle)
        return jsonify(rows)

    @app.route("/api/plantes/search")
    def api_plantes_search():
        from core.plantes_db import PlantesDB
        q = request.args.get("q", "")
        db = PlantesDB()
        rows = db.search(q)
        return jsonify(rows)

    @app.route("/api/plantes/<ident>")
    def api_plantes_detail(ident):
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        row = db.get_plante(ident)
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify(row)

    @app.route("/api/categories")
    def api_categories():
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        return jsonify(db.list_categories())

    @app.route("/api/maladies")
    def api_maladies():
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        plante = request.args.get("plante")
        return jsonify(db.list_maladies(plante))

    @app.route("/api/calendrier")
    def api_calendrier():
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        variete = request.args.get("variete")
        return jsonify(db.get_calendrier(variete))

    @app.route("/api/irrigation-plantes")
    def api_irrigation_plantes():
        from core.plantes_db import PlantesDB
        db = PlantesDB()
        variete = request.args.get("variete")
        cat = request.args.get("categorie")
        return jsonify(db.get_irrigation(variete, cat))

    @app.route("/api/services")
    def api_services():
        from core.services import ServiceManager
        svc = ServiceManager()
        return jsonify(svc.status())

    @app.route("/api/autostart", methods=["GET"])
    def api_autostart_status():
        from core.services import ServiceManager
        svc = ServiceManager()
        return jsonify(svc.autostart_status())

    @app.route("/api/autostart/install", methods=["POST"])
    def api_autostart_install():
        from core.services import ServiceManager
        svc = ServiceManager()
        return jsonify(svc.autostart_install())

    @app.route("/api/autostart/remove", methods=["POST"])
    def api_autostart_remove():
        from core.services import ServiceManager
        svc = ServiceManager()
        return jsonify(svc.autostart_remove())

    @app.route("/api/services/<name>/<action>", methods=["POST"])
    def api_service_action(name, action):
        from core.services import ServiceManager
        svc = ServiceManager()
        if action == "start":
            return jsonify(svc.start(name))
        elif action == "stop":
            return jsonify(svc.stop(name))
        elif action == "restart":
            return jsonify(svc.restart(name))
        elif action == "logs":
            tail = request.args.get("tail", 50, type=int)
            return svc.logs(name, tail), 200, {"Content-Type": "text/plain"}
        return jsonify({"error": f"Unknown action: {action}"}), 400

    @app.route("/api/health")
    def api_health():
        from core.services import ServiceManager
        svc = ServiceManager()
        return jsonify(svc.health())

    @app.route("/api/config")
    def api_config():
        return jsonify(config.data)

    @app.route("/api/config", methods=["POST"])
    def api_config_set():
        data = request.get_json()
        key = data.get("key")
        value = data.get("value")
        if key and value:
            config.set(key, value)
            return jsonify({"status": "ok", "key": key, "value": value})
        return jsonify({"error": "key and value required"}), 400

    def main():
        port = int(os.environ.get("PIXELOS_WEB_PORT", 9999))
        debug = os.environ.get("PIXELOS_DEBUG", "0") == "1"
        print(f"PixelOS Web - http://0.0.0.0:{port}")
        app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    if HAS_FLASK:
        main()
    else:
        print("pip install pixelos[web] pour le dashboard web")
