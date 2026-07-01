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
    print("[!]  Flask non installé: 'pip install pixelos[web]'")
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

    # Routes fédération (réseau mondial PixelOS)
    try:
        from core.federation.hub import register_federation_routes
        register_federation_routes(app)
    except Exception:
        pass

    # Routes Pixel Office Suite (Access, Word, Excel)
    try:
        from core.office.routes import register_office_routes
        register_office_routes(app)
    except Exception:
        pass

    # Routes Web3 (Wallet, Paiement, Exchange, IPFS)
    try:
        from core.web3.routes import register_web3_routes
        register_web3_routes(app)
    except Exception as e:
        print(f"[!]  Web3 routes non chargées: {e}")

    # Routes Pixel Comms (Matrix, chat, vidéo, IoT bridge)
    try:
        from core.comms import register_comms_routes
        register_comms_routes(app)
    except Exception as e:
        print(f"[!]  Comms routes non chargées: {e}")

    # Routes Souveraineté (Charte, DDNS, Disclaimer)
    try:
        from core.sovereignty import register_sovereignty_routes
        register_sovereignty_routes(app)
    except Exception as e:
        print(f"[!]  Sovereignty routes non chargées: {e}")

    # Routes Sécurité & Défense (PixStat, PixDefend, PixScudo)
    try:
        from core.security import register_security_routes
        register_security_routes(app)
    except Exception as e:
        print(f"[!]  Security routes non chargées: {e}")

    # Routes Process Manager (PixManager — list, kill, trace, monitor)
    try:
        from core.process_manager.routes import register_process_manager_routes
        register_process_manager_routes(app)
    except Exception as e:
        print(f"[!]  Process Manager routes non chargées: {e}")

    # Routes Navigateur NOP (Web3 + Privacy + Wallet)
    try:
        from core.browser.routes import register_browser_routes
        register_browser_routes(app)
    except Exception as e:
        print(f"[!]  NOP Browser routes non chargées: {e}")

    # Routes PixNet (Internet Souverain P2P)
    try:
        from core.pixnet.routes import register_pixnet_routes
        register_pixnet_routes(app)
    except Exception as e:
        print(f"[!]  PixNet routes non chargées: {e}")

    # Routes PixBackup (sauvegarde chiffrée)
    try:
        from core.backup.routes import register_backup_routes
        register_backup_routes(app)
    except Exception as e:
        print(f"[!]  PixBackup routes non chargées: {e}")

    # Routes PixAuto (automatisation NL)
    try:
        from core.pixauto.routes import register_pixauto_routes
        register_pixauto_routes(app)
    except Exception as e:
        print(f"[!]  PixAuto routes non chargées: {e}")

    # Routes PixHAL (Hardware Abstraction Layer)
    try:
        from core.pixhal.routes import register_pixhal_routes
        register_pixhal_routes(app)
    except Exception as e:
        print(f"[!]  PixHAL routes non chargées: {e}")

    # Routes PixKey (authentification physique)
    try:
        from core.pixkey.routes import register_pixkey_routes
        register_pixkey_routes(app)
    except Exception as e:
        print(f"[!]  PixKey routes non chargées: {e}")

    # Routes PixDAO (gouvernance décentralisée)
    try:
        from core.pixdao.routes import register_pixdao_routes
        register_pixdao_routes(app)
    except Exception as e:
        print(f"[!]  PixDAO routes non chargées: {e}")

    # Routes Digital Twin (jumeau numérique)
    try:
        from core.digital_twin.routes import register_twin_routes
        register_twin_routes(app)
    except Exception as e:
        print(f"[!]  Digital Twin routes non chargées: {e}")

    # Routes Zero-Touch Installer
    try:
        from core.boot.routes import register_install_routes
        register_install_routes(app)
    except Exception as e:
        print(f"[!]  Installer routes non chargées: {e}")

    # Routes PixOrchestrator
    try:
        from core.orchestrator_routes import register_orchestrator_routes
        register_orchestrator_routes(app)
    except Exception as e:
        print(f"[!]  PixOrchestrator routes non chargées: {e}")

    # Routes PixDHT Query Engine
    try:
        from core.pixdht_routes import register_pixdht_routes
        register_pixdht_routes(app)
    except Exception as e:
        print(f"[!]  PixDHT routes non chargées: {e}")

    # Routes PixStat / Heartbeat
    try:
        from core.pixstat_routes import register_pixstat_routes
        register_pixstat_routes(app)
    except Exception as e:
        print(f"[!]  PixStat routes non chargées: {e}")

    # Routes PixDefend
    try:
        from core.pixdefend_routes import register_pixdefend_routes
        register_pixdefend_routes(app)
    except Exception as e:
        print(f"[!]  PixDefend routes non chargées: {e}")

    # Routes PixScudo
    try:
        from core.pixscudo_routes import register_pixscudo_routes
        register_pixscudo_routes(app)
    except Exception as e:
        print(f"[!]  PixScudo routes non chargées: {e}")

    # Routes IPC Bus
    try:
        from core.ipc_routes import register_ipc_routes
        register_ipc_routes(app)
    except Exception as e:
        print(f"[!]  IPC routes non chargées: {e}")

    # Routes Image Editor (OpenCV Python engine)
    try:
        from core.image_editor.routes import register_image_editor_routes
        register_image_editor_routes(app)
    except Exception as e:
        print(f"[!]  Image Editor routes non chargées: {e}")

    # Routes Video Editor (FFmpeg/OpenCV engine)
    try:
        from core.video_editor.routes import register_video_editor_routes
        register_video_editor_routes(app)
    except Exception as e:
        print(f"[!]  Video Editor routes non chargées: {e}")

    # Routes Audio Editor (SDL2/FFTW3 engine)
    try:
        from core.audio_editor.routes import register_audio_editor_routes
        register_audio_editor_routes(app)
    except Exception as e:
        print(f"[!]  Audio Editor routes non chargées: {e}")

    # Routes PixBalloon (jeu de divertissement robotique)
    try:
        from core.games.routes import register_game_routes
        register_game_routes(app)
    except Exception as e:
        print(f"[!]  PixBalloon routes non chargées: {e}")

    # Routes PixVision (scanner IoT détection d'objets connectés)
    try:
        from core.pixvision.routes import register_pixvision_routes
        register_pixvision_routes(app)
    except Exception as e:
        print(f"[!]  PixVision routes non chargées: {e}")

    # Routes PixDDS (distribution de données pour essaims)
    try:
        from core.pixdds.routes import register_pixdds_routes
        register_pixdds_routes(app)
    except Exception as e:
        print(f"[!]  PixDDS routes non chargées: {e}")

    # Routes PixSwarm (orchestrateur d'essaim robotique)
    try:
        from core.pixswarm.routes import register_pixswarm_routes
        register_pixswarm_routes(app)
    except Exception as e:
        print(f"[!]  PixSwarm routes non chargées: {e}")

    # Routes PixMode (gestionnaire de modes de contrôle)
    try:
        from core.pixmode.routes import register_pixmode_routes
        register_pixmode_routes(app)
    except Exception as e:
        print(f"[!]  PixMode routes non chargées: {e}")

    # Routes PixEngineer (orchestrateur de maintenance)
    try:
        from core.pixengineer.routes import register_pixengineer_routes
        register_pixengineer_routes(app)
    except Exception as e:
        print(f"[!]  PixEngineer routes non chargées: {e}")

    # Routes PixHardwareMap (visualisation 3D)
    try:
        from core.pixhardwaremap.routes import register_pixhardwaremap_routes
        register_pixhardwaremap_routes(app)
    except Exception as e:
        print(f"[!]  PixHardwareMap routes non chargées: {e}")

    # Routes PixBlackBox (enregistreur de vol)
    try:
        from core.pixblackbox.routes import register_pixblackbox_routes
        register_pixblackbox_routes(app)
    except Exception as e:
        print(f"[!]  PixBlackBox routes non chargées: {e}")

    # Routes PixPowerManager (gestion des cycles de charge/repos)
    try:
        from core.pixpowermanager.routes import register_pixpowermanager_routes
        register_pixpowermanager_routes(app)
    except Exception as e:
        print(f"[!]  PixPowerManager routes non chargées: {e}")

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

    # ── Programmes : Text / Audio / Video ──────────────────

    @app.route("/tasks")
    def tasks_page():
        return render_template("tasks.html", title="Taches")

    @app.route("/api/tasks", methods=["GET"])
    def api_tasks_list():
        from core.tasks import TaskManager
        tm = TaskManager()
        q = request.args.get("q")
        status = request.args.get("status")
        cat = request.args.get("categorie")
        prio = request.args.get("priorite")
        zone = request.args.get("zone")
        if q or status or cat or prio or zone:
            return jsonify(tm.search(q, status, cat, prio, zone))
        return jsonify(tm.all())

    @app.route("/api/tasks", methods=["POST"])
    def api_task_create():
        from core.tasks import TaskManager
        data = request.get_json()
        if not data or not data.get("title"):
            return jsonify({"error": "title required"}), 400
        tm = TaskManager()
        t = tm.create(data["title"], data.get("description", ""),
                      data.get("categorie", "autre"),
                      data.get("priorite", "medium"),
                      data.get("echeance"), data.get("assigne", ""),
                      data.get("zone", ""), data.get("plante", ""))
        return jsonify(t), 201

    @app.route("/api/tasks/<task_id>", methods=["PUT"])
    def api_task_update(task_id):
        from core.tasks import TaskManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        tm = TaskManager()
        t = tm.update(task_id, **data)
        if not t:
            return jsonify({"error": "not found"}), 404
        return jsonify(t)

    @app.route("/api/tasks/<task_id>", methods=["DELETE"])
    def api_task_delete(task_id):
        from core.tasks import TaskManager
        tm = TaskManager()
        if tm.delete(task_id):
            return jsonify({"status": "deleted"})
        return jsonify({"error": "not found"}), 404

    @app.route("/api/tasks/stats", methods=["GET"])
    def api_tasks_stats():
        from core.tasks import TaskManager
        tm = TaskManager()
        return jsonify(tm.stats())

    @app.route("/api/tasks/board", methods=["GET"])
    def api_tasks_board():
        from core.tasks import TaskManager
        tm = TaskManager()
        return jsonify(tm.list_by_status())

    # ── Geothermal ─────────────────────────────────────────

    @app.route("/geothermal")
    def geothermal_page():
        return render_template("geothermal.html", title="Geothermal")

    @app.route("/api/geothermal", methods=["GET"])
    def api_geothermal_list():
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        return jsonify(gm.list_zones())

    @app.route("/api/geothermal/summary", methods=["GET"])
    def api_geothermal_summary():
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        return jsonify(gm.summary())

    @app.route("/api/geothermal/cycle", methods=["POST"])
    def api_geothermal_cycle():
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        results = gm.run_cycle()
        return jsonify(results)

    @app.route("/api/geothermal/anomalies", methods=["GET"])
    def api_geothermal_anomalies():
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        return jsonify(gm.check_anomalies())

    @app.route("/api/geothermal/<zone_id>", methods=["GET"])
    def api_geothermal_zone(zone_id):
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        z = gm.get_zone(zone_id)
        if not z:
            return jsonify({"error": "not found"}), 404
        return jsonify(z)

    @app.route("/api/geothermal/<zone_id>/toggle", methods=["POST"])
    def api_geothermal_toggle(zone_id):
        from core.geothermal import GeothermalManager
        gm = GeothermalManager()
        z = gm.get_zone(zone_id)
        if not z:
            return jsonify({"error": "not found"}), 404
        z = gm.update_zone(zone_id, enabled=not z["enabled"])
        return jsonify(z)

    @app.route("/api/geothermal/<zone_id>", methods=["PUT"])
    def api_geothermal_update(zone_id):
        from core.geothermal import GeothermalManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        gm = GeothermalManager()
        z = gm.update_zone(zone_id, **data)
        if not z:
            return jsonify({"error": "not found"}), 404
        return jsonify(z)

    # ── Energy ──────────────────────────────────────────────

    @app.route("/energy")
    def energy_page():
        return render_template("energy.html", title="Energy")

    @app.route("/api/energy", methods=["GET"])
    def api_energy():
        from core.energy import EnergyManager
        em = EnergyManager()
        return jsonify(em.summary())

    @app.route("/api/energy/solar", methods=["GET"])
    def api_energy_solar():
        from core.energy import EnergyManager
        em = EnergyManager()
        return jsonify(em.list_panels())

    @app.route("/api/energy/solar/update", methods=["POST"])
    def api_energy_solar_update():
        from core.energy import EnergyManager
        em = EnergyManager()
        data = request.get_json(silent=True) or {}
        if "ambient_temp" in data:
            em.set_ambient_temp(data["ambient_temp"])
        return jsonify(em.update_solar())

    @app.route("/api/energy/battery", methods=["GET"])
    def api_energy_battery():
        from core.energy import EnergyManager
        em = EnergyManager()
        return jsonify(em.battery.snapshot())

    @app.route("/api/energy/loads", methods=["GET"])
    def api_energy_loads():
        from core.energy import EnergyManager
        em = EnergyManager()
        return jsonify(em.list_loads())

    @app.route("/api/energy/loads/<load_id>", methods=["PUT"])
    def api_energy_load_update(load_id):
        from core.energy import EnergyManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        em = EnergyManager()
        result = em.set_load_state(load_id, data.get("state", "on"),
                                   throttle=data.get("throttle"))
        if not result:
            return jsonify({"error": "not found"}), 404
        return jsonify(result)

    @app.route("/api/energy/cycle", methods=["POST"])
    def api_energy_cycle():
        from core.energy import EnergyManager
        em = EnergyManager()
        data = request.get_json(silent=True) or {}
        if "ambient_temp" in data:
            em.set_ambient_temp(data["ambient_temp"])
        return jsonify(em.run_cycle())

    @app.route("/api/energy/forecast", methods=["GET"])
    def api_energy_forecast():
        from core.energy import EnergyManager
        em = EnergyManager()
        hours = request.args.get("hours", 24, type=int)
        return jsonify(em.forecast(hours))

    @app.route("/api/energy/history", methods=["GET"])
    def api_energy_history():
        from core.energy import EnergyManager
        em = EnergyManager()
        limit = request.args.get("limit", 120, type=int)
        return jsonify(em.get_history(limit))

    @app.route("/api/energy/grid", methods=["PUT"])
    def api_energy_grid():
        from core.energy import EnergyManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        em = EnergyManager()
        em.set_grid(data.get("available", False), data.get("power_w", 0.0))
        return jsonify({"grid_available": em.grid_available,
                         "grid_power_w": em.grid_power_w})

    # ── Spaces ──────────────────────────────────────────────

    @app.route("/spaces")
    def spaces_page():
        return render_template("spaces.html", title="Espaces")

    @app.route("/api/spaces", methods=["GET"])
    def api_spaces():
        from core.spaces import SpaceManager
        sm = SpaceManager()
        return jsonify(sm.summary())

    @app.route("/api/spaces/list", methods=["GET"])
    def api_spaces_list():
        from core.spaces import SpaceManager
        sm = SpaceManager()
        return jsonify(sm.list_espaces())

    @app.route("/api/spaces/<espace_id>", methods=["GET"])
    def api_spaces_espace(espace_id):
        from core.spaces import SpaceManager
        sm = SpaceManager()
        e = sm.get_espace(espace_id)
        if not e:
            return jsonify({"error": "not found"}), 404
        return jsonify(e)

    @app.route("/api/spaces/<espace_id>/sensors", methods=["POST"])
    def api_spaces_read_sensors(espace_id):
        from core.spaces import SpaceManager
        sm = SpaceManager()
        return jsonify(sm.read_sensors(espace_id))

    @app.route("/api/spaces/<espace_id>/controls/<control_id>", methods=["PUT"])
    def api_spaces_control(espace_id, control_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.control_action(espace_id, control_id,
                              data.get("action", "on"), data.get("value"))
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/spaces/<espace_id>/zones/<sub_zone_id>/assign", methods=["PUT"])
    def api_spaces_assign(espace_id, sub_zone_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        if "product_id" not in data:
            return jsonify({"error": "product_id required"}), 400
        sm = SpaceManager()
        r = sm.assign_product(espace_id, sub_zone_id,
                               data["product_id"], data.get("planted_at"))
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/spaces/add", methods=["POST"])
    def api_spaces_add():
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.add_espace(
            data.get("espace_id", ""),
            data.get("type", "serre"),
            data.get("label", ""),
            data.get("location", ""),
            data.get("description", ""),
            confirm=data.get("confirm", False))
        if "error" in r:
            return jsonify(r), 400 if r.get("status") != "pending_confirmation" else 202
        return jsonify(r), 201

    @app.route("/api/spaces/<espace_id>/remove", methods=["POST"])
    def api_spaces_remove(espace_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.remove_espace(espace_id, confirm=data.get("confirm", False))
        if isinstance(r, tuple):
            return jsonify(r[0]), r[1]
        return jsonify(r)

    @app.route("/api/spaces/<espace_id>/sensors/add", methods=["POST"])
    def api_spaces_sensor_add(espace_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.add_sensor_to_espace(espace_id, data.get("sensor_id", ""),
                                     data.get("type", "temperature"),
                                     data.get("label", ""),
                                     data.get("bus", "simulation"),
                                     data.get("addr"))
        if isinstance(r, tuple):
            return jsonify(r[0]), r[1]
        return jsonify(r), 201

    @app.route("/api/spaces/<espace_id>/sensors/<sensor_id>/remove", methods=["POST"])
    def api_spaces_sensor_remove(espace_id, sensor_id):
        from core.spaces import SpaceManager
        sm = SpaceManager()
        r = sm.remove_sensor(espace_id, sensor_id)
        if isinstance(r, tuple):
            return jsonify(r[0]), r[1]
        return jsonify(r)

    @app.route("/api/spaces/<espace_id>/controls/add", methods=["POST"])
    def api_spaces_control_add(espace_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.add_control_to_espace(espace_id, data.get("control_id", ""),
                                      data.get("type", "vanne_irrigation"),
                                      data.get("label", ""),
                                      data.get("pin"),
                                      data.get("auto_mode", False))
        if isinstance(r, tuple):
            return jsonify(r[0]), r[1]
        return jsonify(r), 201

    @app.route("/api/spaces/<espace_id>/controls/<control_id>/remove", methods=["POST"])
    def api_spaces_control_remove(espace_id, control_id):
        from core.spaces import SpaceManager
        sm = SpaceManager()
        r = sm.remove_control(espace_id, control_id)
        if isinstance(r, tuple):
            return jsonify(r[0]), r[1]
        return jsonify(r)

    @app.route("/api/spaces/<espace_id>/controls/auto", methods=["PUT"])
    def api_spaces_auto(espace_id):
        from core.spaces import SpaceManager
        data = request.get_json(silent=True) or {}
        sm = SpaceManager()
        r = sm.set_auto_mode(espace_id, data.get("auto_type", "irrigation"),
                              data.get("enabled", False))
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    # ── Lifecycle / Products ────────────────────────────────

    @app.route("/products")
    def products_page():
        return render_template("products.html", title="Produits")

    @app.route("/api/products", methods=["GET"])
    def api_products():
        from core.lifecycle import LifecycleManager
        lm = LifecycleManager()
        return jsonify(lm.list_products())

    @app.route("/api/products/<product_id>", methods=["GET"])
    def api_product(product_id):
        from core.lifecycle import LifecycleManager
        lm = LifecycleManager()
        p = lm.get_product(product_id)
        if not p:
            return jsonify({"error": "not found"}), 404
        return jsonify(p)

    @app.route("/api/plantations", methods=["GET"])
    def api_plantations():
        from core.lifecycle import LifecycleManager
        lm = LifecycleManager()
        return jsonify(lm.list_plantations())

    @app.route("/api/plantations", methods=["POST"])
    def api_plantation_create():
        from core.lifecycle import LifecycleManager
        data = request.get_json(silent=True)
        if not data or "product_id" not in data or "espace_id" not in data:
            return jsonify({"error": "product_id and espace_id required"}), 400
        lm = LifecycleManager()
        pl = lm.create_plantation(
            data["product_id"], data["espace_id"],
            data.get("sub_zone_id", ""), data.get("quantity", 1),
            data.get("label", ""), data.get("planted_at"))
        return jsonify(pl), 201

    @app.route("/api/plantations/<plantation_id>", methods=["GET"])
    def api_plantation(plantation_id):
        from core.lifecycle import LifecycleManager
        lm = LifecycleManager()
        pl = lm.get_plantation(plantation_id)
        if not pl:
            return jsonify({"error": "not found"}), 404
        return jsonify(pl)

    @app.route("/api/plantations/<plantation_id>", methods=["PUT"])
    def api_plantation_update(plantation_id):
        from core.lifecycle import LifecycleManager
        data = request.get_json(silent=True) or {}
        lm = LifecycleManager()
        pl = lm.update_plantation(plantation_id, **data)
        if not pl:
            return jsonify({"error": "not found"}), 404
        return jsonify(pl)

    @app.route("/api/lifecycle/generate-tasks", methods=["POST"])
    def api_lifecycle_generate():
        from core.lifecycle import LifecycleManager
        data = request.get_json(silent=True) or {}
        lm = LifecycleManager()
        tasks = lm.generate_tasks(data.get("plantation_id"),
                                  data.get("force", False))
        return jsonify(tasks)

    @app.route("/api/lifecycle/suggestions", methods=["GET"])
    def api_lifecycle_suggestions():
        from core.lifecycle import LifecycleManager
        lm = LifecycleManager()
        espace = request.args.get("espace_id")
        return jsonify(lm.get_suggestions(espace))

    @app.route("/api/tasks/alerts", methods=["GET"])
    def api_tasks_alerts():
        from core.tasks import TaskManager
        tm = TaskManager()
        return jsonify(tm.alerts())

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    def api_task_get(task_id):
        from core.tasks import TaskManager
        tm = TaskManager()
        t = tm.get(task_id)
        if not t:
            return jsonify({"error": "not found"}), 404
        return jsonify(t)

    @app.route("/programs/text")
    def programs_text_page():
        return render_template("text.html", title="Notes")

    @app.route("/programs/audio")
    def programs_audio_page():
        return render_template("audio.html", title="Audio")

    @app.route("/programs/video")
    def programs_video_page():
        return render_template("video.html", title="Video")

    @app.route("/api/programs/notes", methods=["GET"])
    def api_notes_list():
        from core.programs import ProgramManager
        pm = ProgramManager()
        cat = request.args.get("categorie")
        q = request.args.get("q")
        if q:
            notes = pm.note_search(q)
        else:
            notes = pm.notes_list()
        if cat:
            notes = [n for n in notes if n.get("categorie") == cat]
        return jsonify(notes)

    @app.route("/api/programs/notes", methods=["POST"])
    def api_note_create():
        from core.programs import ProgramManager
        data = request.get_json()
        if not data or not data.get("title"):
            return jsonify({"error": "title required"}), 400
        pm = ProgramManager()
        note = pm.note_create(data["title"], data.get("content", ""),
                              data.get("categorie", "general"))
        return jsonify(note), 201

    @app.route("/api/programs/notes/<note_id>", methods=["GET"])
    def api_note_get(note_id):
        from core.programs import ProgramManager
        pm = ProgramManager()
        note = pm.note_get(note_id)
        if not note:
            return jsonify({"error": "not found"}), 404
        return jsonify(note)

    @app.route("/api/programs/notes/<note_id>", methods=["PUT"])
    def api_note_update(note_id):
        from core.programs import ProgramManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        pm = ProgramManager()
        note = pm.note_update(note_id, data.get("title"),
                              data.get("content"), data.get("categorie"))
        if not note:
            return jsonify({"error": "not found"}), 404
        return jsonify(note)

    @app.route("/api/programs/notes/<note_id>", methods=["DELETE"])
    def api_note_delete(note_id):
        from core.programs import ProgramManager
        pm = ProgramManager()
        if pm.note_delete(note_id):
            return jsonify({"status": "deleted"})
        return jsonify({"error": "not found"}), 404

    @app.route("/api/programs/notes/categories", methods=["GET"])
    def api_notes_categories():
        from core.programs import ProgramManager
        pm = ProgramManager()
        return jsonify(pm.note_categories())

    @app.route("/api/programs/audio", methods=["GET"])
    def api_audio_list():
        from core.programs import ProgramManager
        pm = ProgramManager()
        return jsonify(pm.audio_list())

    @app.route("/api/programs/audio", methods=["POST"])
    def api_audio_upload():
        from core.programs import ProgramManager
        pm = ProgramManager()
        if "file" not in request.files:
            return jsonify({"error": "no file"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "empty file"}), 400
        from core.programs import AUDIO_DIR
        fpath = AUDIO_DIR / f.filename
        f.save(fpath)
        entry = pm.audio_add(f.filename, request.form.get("title"),
                             float(request.form.get("duration", 0)),
                             fpath.stat().st_size)
        return jsonify(entry), 201

    @app.route("/api/programs/audio/<audio_id>", methods=["GET"])
    def api_audio_serve(audio_id):
        from core.programs import ProgramManager
        pm = ProgramManager()
        fpath = pm.audio_path(audio_id)
        if not fpath:
            return jsonify({"error": "not found"}), 404
        from flask import send_file
        return send_file(fpath, mimetype="audio/webm")

    @app.route("/api/programs/audio/<audio_id>", methods=["DELETE"])
    def api_audio_delete(audio_id):
        from core.programs import ProgramManager
        pm = ProgramManager()
        if pm.audio_delete(audio_id):
            return jsonify({"status": "deleted"})
        return jsonify({"error": "not found"}), 404

    @app.route("/api/programs/video", methods=["GET"])
    def api_video_list():
        from core.programs import ProgramManager
        pm = ProgramManager()
        return jsonify(pm.video_list())

    @app.route("/api/programs/video", methods=["POST"])
    def api_video_add():
        from core.programs import ProgramManager
        data = request.get_json()
        if not data or not data.get("source"):
            return jsonify({"error": "source required"}), 400
        pm = ProgramManager()
        entry = pm.video_add(data["source"], data.get("title"),
                             data.get("source_type", "url"),
                             data.get("duration", 0))
        return jsonify(entry), 201

    @app.route("/api/programs/video/<video_id>", methods=["PUT"])
    def api_video_update(video_id):
        from core.programs import ProgramManager
        data = request.get_json()
        pm = ProgramManager()
        v = pm.video_update(video_id, data.get("title") if data else None,
                            data.get("source") if data else None)
        if not v:
            return jsonify({"error": "not found"}), 404
        return jsonify(v)

    @app.route("/api/programs/video/<video_id>", methods=["DELETE"])
    def api_video_delete(video_id):
        from core.programs import ProgramManager
        pm = ProgramManager()
        if pm.video_delete(video_id):
            return jsonify({"status": "deleted"})
        return jsonify({"error": "not found"}), 404

    # ── Harvest / Inventory ───────────────────────────────────

    @app.route("/harvest")
    def harvest_page():
        return render_template("harvest.html", title="Recolte")

    @app.route("/inventory")
    def inventory_page():
        return render_template("inventory.html", title="Inventaire")

    @app.route("/api/harvest/summary", methods=["GET"])
    def api_harvest_summary():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        return jsonify(hm.summary())

    @app.route("/api/harvest/lines", methods=["GET"])
    def api_harvest_lines():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        return jsonify(hm.list_lines())

    @app.route("/api/harvest/lines/<line_id>", methods=["GET"])
    def api_harvest_line(line_id):
        from core.harvest import HarvestManager
        hm = HarvestManager()
        l = hm.get_line(line_id)
        if not l:
            return jsonify({"error": "not found"}), 404
        return jsonify(l)

    @app.route("/api/harvest/estimate", methods=["POST"])
    def api_harvest_estimate():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        results = hm.estimate_all()
        return jsonify({"results": results, "predictions": hm.predict_by_zone()})

    @app.route("/api/harvest/predict", methods=["GET"])
    def api_harvest_predict():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        zone = request.args.get("zone")
        return jsonify(hm.predict_by_zone(zone))

    @app.route("/api/harvest/batches", methods=["GET"])
    def api_harvest_batches():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        status = request.args.get("status")
        return jsonify(hm.list_batches(status))

    @app.route("/api/harvest/batches", methods=["POST"])
    def api_harvest_batch_create():
        from core.harvest import HarvestManager
        data = request.get_json()
        if not data or not data.get("line_id") or not data.get("weight_kg"):
            return jsonify({"error": "line_id and weight_kg required"}), 400
        hm = HarvestManager()
        b = hm.create_batch(data["line_id"], data["weight_kg"],
                           data.get("unit_price"), data.get("quality", "A"),
                           data.get("harvest_date"))
        if not b:
            return jsonify({"error": "line not found or inactive"}), 404
        return jsonify(b), 201

    @app.route("/api/harvest/batches/<batch_id>", methods=["GET"])
    def api_harvest_batch(batch_id):
        from core.harvest import HarvestManager
        hm = HarvestManager()
        b = hm.get_batch(batch_id)
        if not b:
            return jsonify({"error": "not found"}), 404
        return jsonify(b)

    @app.route("/api/harvest/batches/<batch_id>", methods=["PUT"])
    def api_harvest_batch_update(batch_id):
        from core.harvest import HarvestManager
        data = request.get_json(silent=True) or {}
        hm = HarvestManager()
        b = hm.update_batch(batch_id, **data)
        if not b:
            return jsonify({"error": "not found"}), 404
        return jsonify(b)

    @app.route("/api/harvest/labels/<batch_id>", methods=["GET"])
    def api_harvest_labels(batch_id):
        from core.harvest import HarvestManager
        hm = HarvestManager()
        return jsonify(hm.get_labels_for_batch(batch_id))

    @app.route("/api/harvest/suggestions", methods=["GET"])
    def api_harvest_suggestions():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        return jsonify(hm.get_harvest_suggestions())

    @app.route("/api/harvest/inventory", methods=["GET"])
    def api_harvest_inventory():
        from core.harvest import HarvestManager
        hm = HarvestManager()
        return jsonify(hm.inventory.snapshot())

    # ── Cultivation (orchestration transverse) ─────────────────

    @app.route("/api/cultivation/monitor", methods=["POST"])
    def api_cultivation_monitor():
        from core.cultivation import CultivationManager
        cm = CultivationManager()
        return jsonify(cm.smart_monitor())

    @app.route("/api/cultivation/report", methods=["GET"])
    def api_cultivation_report():
        from core.cultivation import CultivationManager
        cm = CultivationManager()
        espace = request.args.get("espace_id")
        plantation = request.args.get("plantation_id")
        return jsonify(cm.culture_report(espace, plantation))

    @app.route("/api/cultivation/suggestions", methods=["GET"])
    def api_cultivation_suggestions():
        from core.cultivation import CultivationManager
        cm = CultivationManager()
        return jsonify(cm.all_suggestions())

    @app.route("/api/cultivation/status", methods=["GET"])
    def api_cultivation_status():
        from core.cultivation import CultivationManager
        cm = CultivationManager()
        return jsonify(cm.global_status())

    # ── TimescaleDB (time-series primary backend) ──────────────

    @app.route("/api/tsdb/stats", methods=["GET"])
    def api_tsdb_stats():
        from core.bgdatasys import bgdatasys
        return jsonify(bgdatasys.stats().get("tsdb", {}))

    @app.route("/api/tsdb/query", methods=["GET"])
    def api_tsdb_query():
        from core.bgdatasys import bgdatasys
        space = request.args.get("space")
        sensor = request.args.get("sensor")
        hours = int(request.args.get("hours", 24))
        source = request.args.get("source", "timescaledb")
        rows = bgdatasys.query_sensors(space, sensor, hours, source=source)
        return jsonify(rows)

    @app.route("/api/tsdb/write", methods=["POST"])
    def api_tsdb_write():
        from core.bgdatasys import bgdatasys
        data = request.get_json()
        if not data or not data.get("sensor_id") or data.get("value") is None:
            return jsonify({"error": "sensor_id and value required"}), 400
        bgdatasys.write_measurement(
            data.get("space_id", ""), data["sensor_id"],
            data["value"], data.get("unit", ""), data.get("tags"))
        return jsonify({"status": "ok"}), 201

    @app.route("/api/tsdb/hourly", methods=["GET"])
    def api_tsdb_hourly():
        from core.bgdatasys import bgdatasys
        space = request.args.get("space")
        sensor = request.args.get("sensor")
        hours = int(request.args.get("hours", 168))
        rows = bgdatasys.hourly_avg(space, sensor, hours)
        return jsonify(rows)

    @app.route("/api/tsdb/daily", methods=["GET"])
    def api_tsdb_daily():
        from core.bgdatasys import bgdatasys
        space = request.args.get("space")
        sensor = request.args.get("sensor")
        days = int(request.args.get("days", 90))
        rows = bgdatasys.daily_avg(space, sensor, days)
        return jsonify(rows)

    @app.route("/api/tsdb/sensors", methods=["GET"])
    def api_tsdb_sensors():
        from core.bgdatasys import bgdatasys
        space = request.args.get("space")
        stype = request.args.get("type")
        return jsonify(bgdatasys.list_sensors(space, stype))

    @app.route("/api/tsdb/register", methods=["POST"])
    def api_tsdb_register():
        from core.bgdatasys import bgdatasys
        data = request.get_json()
        if not data or not data.get("sensor_id"):
            return jsonify({"error": "sensor_id required"}), 400
        ok = bgdatasys.register_sensor(
            data["sensor_id"], data.get("space_id", ""),
            data.get("sensor_type", "unknown"), data.get("label", ""),
            data.get("unit", ""), data.get("bus", "simulation"),
            data.get("addr", ""), data.get("metadata"))
        return jsonify({"status": "ok" if ok else "error"}), 201 if ok else 500

    @app.route("/api/tsdb/event", methods=["POST"])
    def api_tsdb_event():
        from core.bgdatasys import bgdatasys
        data = request.get_json()
        if not data or not data.get("event_type"):
            return jsonify({"error": "event_type required"}), 400
        bgdatasys.write_event(
            data["event_type"], data.get("space_id", ""),
            data.get("sensor_id", ""), data.get("actor", ""),
            data.get("value", ""), data.get("details"))
        return jsonify({"status": "ok"}), 201

    @app.route("/api/tsdb/events", methods=["GET"])
    def api_tsdb_events():
        from core.bgdatasys import bgdatasys
        etype = request.args.get("type")
        space = request.args.get("space")
        hours = int(request.args.get("hours", 72))
        return jsonify(bgdatasys.query_events(etype, space, hours))

    @app.route("/api/tsdb/migrate", methods=["POST"])
    def api_tsdb_migrate():
        from core.bgdatasys import bgdatasys
        data = request.get_json(silent=True) or {}
        hours = int(data.get("hours", 720))
        result = bgdatasys.migrate_from_mongodb(hours)
        return jsonify(result)

    @app.route("/api/tsdb/seed", methods=["POST"])
    def api_tsdb_seed():
        from core.bgdatasys import bgdatasys
        data = request.get_json(silent=True) or {}
        days = int(data.get("days", 7))
        interval = int(data.get("interval_minutes", 15))
        result = bgdatasys.seed_test_data(days, interval)
        return jsonify(result)

    @app.route("/api/tsdb/training", methods=["GET"])
    def api_tsdb_training():
        from core.bgdatasys import bgdatasys
        model = request.args.get("model")
        limit = int(request.args.get("limit", 20))
        return jsonify(bgdatasys.list_training_runs(model, limit))

    @app.route("/api/tsdb/predictions", methods=["GET"])
    def api_tsdb_predictions():
        from core.bgdatasys import bgdatasys
        model = request.args.get("model")
        space = request.args.get("space")
        hours = int(request.args.get("hours", 720))
        return jsonify(bgdatasys.query_predictions(model, space, hours))

    # ── BgDataSys (data layer) ─────────────────────────────────

    @app.route("/api/bgdatasys/stats", methods=["GET"])
    def api_bgdatasys_stats():
        from core.bgdatasys import bgdatasys
        return jsonify(bgdatasys.stats())

    @app.route("/api/bgdatasys/measurements", methods=["POST"])
    def api_bgdatasys_write():
        from core.bgdatasys import bgdatasys
        data = request.get_json()
        if not data or not data.get("space_id") or data.get("value") is None:
            return jsonify({"error": "space_id and value required"}), 400
        bgdatasys.write_measurement(
            data["space_id"], data.get("sensor_id", "temp_air"),
            data["value"], data.get("unit", ""), data.get("tags"))
        return jsonify({"status": "ok"}), 201

    @app.route("/api/bgdatasys/query", methods=["GET"])
    def api_bgdatasys_query():
        from core.bgdatasys import bgdatasys
        space = request.args.get("space")
        sensor = request.args.get("sensor")
        hours = int(request.args.get("hours", 24))
        rows = bgdatasys.query_sensors(space, sensor, hours)
        return jsonify(rows)

    @app.route("/api/bgdatasys/mysql", methods=["POST"])
    def api_bgdatasys_mysql():
        from core.bgdatasys import bgdatasys
        data = request.get_json()
        if not data or not data.get("query"):
            return jsonify({"error": "query required"}), 400
        rows = bgdatasys.query_mysql(data["query"], tuple(data.get("params", [])))
        return jsonify(rows)

    # ── ONNX Engine ──────────────────────────────────────────

    @app.route("/api/ml/onnx/stats", methods=["GET"])
    def api_onnx_stats():
        from ml.serving.onnx_engine import OnnxEngine
        engine = OnnxEngine()
        return jsonify(engine.stats())

    @app.route("/api/ml/onnx/export", methods=["POST"])
    def api_onnx_export():
        from ml.serving.onnx_engine import OnnxEngine
        data = request.get_json(silent=True) or {}
        engine = OnnxEngine(data.get("model", "irrigation_model"))
        result = engine.export_onnx(quantize=data.get("quantize", True))
        return jsonify(result)

    @app.route("/api/ml/onnx/predict", methods=["POST"])
    def api_onnx_predict():
        from ml.serving.onnx_engine import OnnxEngine
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        engine = OnnxEngine()
        return jsonify(engine.predict(data))

    # ── Pipeline auto-retrain ─────────────────────────────────

    @app.route("/api/ml/pipeline/run", methods=["POST"])
    def api_pipeline_run():
        from ml.pipeline import TrainingPipeline
        data = request.get_json(silent=True) or {}
        pl = TrainingPipeline(data.get("model", "irrigation_model"),
                              data.get("zone", "sol_serre"))
        result = pl.run(days=data.get("days", 30),
                        force=data.get("force", False),
                        trigger_task_id=data.get("task_id"))
        return jsonify(result)

    @app.route("/api/ml/pipeline/versions", methods=["GET"])
    def api_pipeline_versions():
        from ml.pipeline import TrainingPipeline
        pl = TrainingPipeline()
        return jsonify(pl.list_versions())

    @app.route("/api/ml/pipeline/rollback", methods=["POST"])
    def api_pipeline_rollback():
        from ml.pipeline import TrainingPipeline
        data = request.get_json(silent=True) or {}
        pl = TrainingPipeline(data.get("model", "irrigation_model"))
        result = pl.rollback(data.get("version"))
        return jsonify(result)

    # ── Lab (Pôle laboratoire) ─────────────────────────────────

    @app.route("/api/lab/stats", methods=["GET"])
    def api_lab_stats():
        from core.laboratory import LabManager
        return jsonify(LabManager().stats())

    @app.route("/api/lab/heatmap", methods=["GET"])
    def api_lab_heatmap():
        from core.laboratory import LabManager
        return jsonify(LabManager().heatmap_data())

    @app.route("/api/lab/samples", methods=["GET"])
    def api_lab_samples():
        from core.laboratory import LabManager
        return jsonify(LabManager().list_samples(
            request.args.get("type"), request.args.get("status"),
            request.args.get("location")))

    @app.route("/api/lab/samples", methods=["POST"])
    def api_lab_sample_create():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        s = LabManager().create_sample(
            data.get("sample_type", "sol"), data.get("source", ""),
            data.get("location", ""), data.get("collector", ""),
            data.get("depth_cm"), data.get("mass_g"), data.get("notes", ""))
        return jsonify(s), 201

    @app.route("/api/lab/samples/<sample_id>", methods=["GET"])
    def api_lab_sample(sample_id):
        from core.laboratory import LabManager
        s = LabManager().get_sample(sample_id)
        if not s:
            return jsonify({"error": "not found"}), 404
        return jsonify(s)

    @app.route("/api/lab/soil", methods=["POST"])
    def api_lab_soil():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data or not data.get("sample_id"):
            return jsonify({"error": "sample_id required"}), 400
        r = LabManager().create_soil_analysis(data["sample_id"], data)
        return jsonify(r), 201

    @app.route("/api/lab/soil/<sample_id>", methods=["GET"])
    def api_lab_soil_get(sample_id):
        from core.laboratory import LabManager
        r = LabManager().get_soil_analysis(sample_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/lab/microbiome", methods=["POST"])
    def api_lab_microbiome():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data or not data.get("sample_id"):
            return jsonify({"error": "sample_id required"}), 400
        r = LabManager().create_microbiome(data["sample_id"], data)
        return jsonify(r), 201

    @app.route("/api/lab/microbiome/<sample_id>", methods=["GET"])
    def api_lab_microbiome_get(sample_id):
        from core.laboratory import LabManager
        r = LabManager().get_microbiome(sample_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/lab/microscopy", methods=["POST"])
    def api_lab_microscopy():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data or not data.get("sample_id"):
            return jsonify({"error": "sample_id required"}), 400
        r = LabManager().create_microscopy(data["sample_id"], data)
        return jsonify(r), 201

    @app.route("/api/lab/microscopy/<observation_id>", methods=["GET"])
    def api_lab_microscopy_get(observation_id):
        from core.laboratory import LabManager
        r = LabManager().get_microscopy(observation_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/lab/growth", methods=["POST"])
    def api_lab_growth():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data or not data.get("plant_id"):
            return jsonify({"error": "plant_id required"}), 400
        lm = LabManager()
        if "track" in data:
            r = lm.create_growth_track(data["plant_id"], data.get("product_id", ""))
        else:
            r = lm.record_growth(
                data["plant_id"], data.get("stage", "croissance_végétative"),
                data.get("height_cm"), data.get("leaf_count"),
                data.get("leaf_area_cm2"), data.get("stem_diameter_mm"),
                data.get("root_length_cm"), data.get("branching_count"),
                data.get("chlorophyll_spad"), data.get("ndvi"),
                data.get("image_path", ""), data.get("notes", ""))
        return jsonify(r), 201

    @app.route("/api/lab/growth/<plant_id>", methods=["GET"])
    def api_lab_growth_get(plant_id):
        from core.laboratory import LabManager
        r = LabManager().growth_summary(plant_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/lab/genetics", methods=["POST"])
    def api_lab_genetics():
        from core.laboratory import LabManager
        data = request.get_json()
        if not data or not data.get("plant_id"):
            return jsonify({"error": "plant_id required"}), 400
        lm = LabManager()
        r = lm.create_genetic_profile(data["plant_id"],
                                       data.get("species", ""),
                                       data.get("variety", ""))
        return jsonify(r), 201

    @app.route("/api/lab/genetics/<plant_id>", methods=["GET"])
    def api_lab_genetics_get(plant_id):
        from core.laboratory import LabManager
        r = LabManager().get_genetic_profile(plant_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    # ── Omics (Bioinformatique) ───────────────────────────────

    @app.route("/api/omics/stats", methods=["GET"])
    def api_omics_stats():
        from core.omics import OmicsPipeline
        return jsonify(OmicsPipeline().stats())

    @app.route("/api/omics/genomes", methods=["GET"])
    def api_omics_genomes():
        from core.omics import OmicsPipeline
        return jsonify(OmicsPipeline().importer.list_genomes(
            request.args.get("species")))

    @app.route("/api/omics/align", methods=["POST"])
    def api_omics_align():
        from core.omics import SequenceAligner
        data = request.get_json()
        if not data or not data.get("seq1") or not data.get("seq2"):
            return jsonify({"error": "seq1 and seq2 required"}), 400
        r = SequenceAligner.pairwise(data["seq1"], data["seq2"])
        return jsonify(r)

    @app.route("/api/omics/diversity", methods=["POST"])
    def api_omics_diversity():
        from core.omics import Metagenomics
        data = request.get_json(silent=True) or {}
        import numpy as np
        otu = np.array(data.get("otu_table", np.random.randint(0, 100, 50)))
        r = Metagenomics().alpha_diversity(otu)
        return jsonify(r)

    # ── Ontology ──────────────────────────────────────────────

    @app.route("/api/ontology/stats", methods=["GET"])
    def api_ontology_stats():
        from core.ontology import ontology
        return jsonify(ontology.stats())

    @app.route("/api/ontology/traits", methods=["GET"])
    def api_ontology_traits():
        from core.ontology import ontology
        return jsonify(ontology.list_all_species())

    @app.route("/api/ontology/traits", methods=["POST"])
    def api_ontology_trait_create():
        from core.ontology import PlantTrait, ontology
        data = request.get_json()
        if not data or not data.get("species_id"):
            return jsonify({"error": "species_id required"}), 400
        pt = PlantTrait(data["species_id"])
        for k, v in data.items():
            if hasattr(pt, k) and k != "species_id":
                setattr(pt, k, v)
        r = ontology.save_plant_trait(pt)
        return jsonify(r), 201

    @app.route("/api/ontology/traits/<species_id>", methods=["GET"])
    def api_ontology_trait_get(species_id):
        from core.ontology import ontology
        r = ontology.get_plant_trait(species_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/ontology/compare", methods=["POST"])
    def api_ontology_compare():
        from core.ontology import ontology
        data = request.get_json()
        if not data or not data.get("species_a") or not data.get("species_b"):
            return jsonify({"error": "species_a and species_b required"}), 400
        r = ontology.compare_species(data["species_a"], data["species_b"])
        if not r:
            return jsonify({"error": "species not found"}), 404
        return jsonify(r)

    @app.route("/api/ontology/export/<species_id>", methods=["GET"])
    def api_ontology_export(species_id):
        from core.ontology import ontology
        r = ontology.export_plant_profile(species_id)
        if not r:
            return jsonify({"error": "not found"}), 404
        return jsonify(r)

    @app.route("/api/ontology/import", methods=["POST"])
    def api_ontology_import():
        from core.ontology import ontology
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400
        r = ontology.import_plant_profile(data)
        return jsonify(r), 201

    @app.route("/api/ontology/exchanges", methods=["GET"])
    def api_ontology_exchanges():
        from core.ontology import ontology
        return jsonify(ontology.list_exchanges(request.args.get("direction")))

    # ── Vision (Computer Vision) ──────────────────────────────

    @app.route("/api/vision/stats", methods=["GET"])
    def api_vision_stats():
        from core.vision import VisionPipeline
        return jsonify(VisionPipeline().stats())

    @app.route("/api/vision/segment", methods=["POST"])
    def api_vision_segment():
        from core.vision import VisionPipeline
        data = request.get_json()
        if not data or not data.get("image"):
            return jsonify({"error": "image path required"}), 400
        return jsonify(VisionPipeline().analyze_plant(data["image"]))

    @app.route("/api/vision/ndvi", methods=["POST"])
    def api_vision_ndvi():
        from core.vision import VisionPipeline
        data = request.get_json()
        if not data or not data.get("nir") or not data.get("red"):
            return jsonify({"error": "nir and red required"}), 400
        return jsonify(VisionPipeline().calculate_ndvi(data["nir"], data["red"]))

    @app.route("/api/vision/root", methods=["POST"])
    def api_vision_root():
        from core.vision import VisionPipeline
        data = request.get_json()
        if not data or not data.get("image"):
            return jsonify({"error": "image path required"}), 400
        return jsonify(VisionPipeline().analyze_root(data["image"]))

    @app.route("/api/vision/disease", methods=["POST"])
    def api_vision_disease():
        from core.vision import VisionPipeline
        data = request.get_json()
        if not data or not data.get("image"):
            return jsonify({"error": "image path required"}), 400
        return jsonify(VisionPipeline().disease.detect_symptoms(data["image"]))

    @app.route("/api/vision/growth", methods=["POST"])
    def api_vision_growth():
        from core.vision import VisionPipeline
        data = request.get_json()
        if not data or not data.get("images"):
            return jsonify({"error": "images list required"}), 400
        return jsonify(VisionPipeline().analyze_growth_series(data["images"]))

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

    # ── AgriProduction ────────────────────────────────────────

    @app.route("/agriproduction")
    def agriproduction_page():
        return render_template("agriproduction.html", title="AgriProduction")

    @app.route("/api/agriproduction/stats", methods=["GET"])
    def api_agriproduction_stats():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.stats())

    @app.route("/api/agriproduction/forecast", methods=["GET"])
    def api_agriproduction_forecast():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        data = request.args
        sensor_data = None
        if data.get("temp") or data.get("hum") or data.get("light"):
            sensor_data = {
                "temp_air": float(data.get("temp", 20)),
                "humidite": float(data.get("hum", 60)),
                "lumiere": float(data.get("light", 25000)),
                "humidite_sol": float(data.get("soil_moist", 45)),
            }
        return jsonify(ap.full_forecast(sensor_data))

    @app.route("/api/agriproduction/readiness", methods=["GET"])
    def api_agriproduction_readiness():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.harvest_readiness())

    @app.route("/api/agriproduction/harvest", methods=["POST"])
    def api_agriproduction_harvest():
        from core.agriproduction import AgriProduction
        data = request.get_json()
        if not data or not data.get("line_id") or not data.get("weight_kg"):
            return jsonify({"error": "line_id and weight_kg required"}), 400
        ap = AgriProduction()
        result = ap.execute_harvest(
            data["line_id"], data["weight_kg"],
            data.get("unit_price"), data.get("quality", "A"),
            data.get("harvest_date"))
        return jsonify(result), 201

    @app.route("/api/agriproduction/sort", methods=["POST"])
    def api_agriproduction_sort():
        from core.agriproduction import AgriProduction
        data = request.get_json()
        if not data or not data.get("batch_id"):
            return jsonify({"error": "batch_id required"}), 400
        ap = AgriProduction()
        result = ap.create_sorting(data["batch_id"],
                                   data.get("method", "manuel"),
                                   data.get("entries"))
        return jsonify(result), 201

    @app.route("/api/agriproduction/sortings", methods=["GET"])
    def api_agriproduction_sortings():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.list_sortings(request.args.get("batch_id")))

    @app.route("/api/agriproduction/order", methods=["POST"])
    def api_agriproduction_order():
        from core.agriproduction import AgriProduction
        data = request.get_json()
        if not data or not data.get("batch_id"):
            return jsonify({"error": "batch_id required"}), 400
        ap = AgriProduction()
        result = ap.create_order(
            data["batch_id"], data.get("product", ""),
            data.get("quantity_kg", 0), data.get("destination", ""),
            data.get("client", ""), data.get("client_ref", ""),
            data.get("unit_price"), data.get("certifications"))
        return jsonify(result), 201

    @app.route("/api/agriproduction/orders", methods=["GET"])
    def api_agriproduction_orders():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.list_orders(
            request.args.get("status"), request.args.get("client")))

    @app.route("/api/agriproduction/orders/<order_id>", methods=["PUT"])
    def api_agriproduction_order_update(order_id):
        from core.agriproduction import AgriProduction
        data = request.get_json(silent=True) or {}
        ap = AgriProduction()
        result = ap.update_order(order_id, **data)
        if not result:
            return jsonify({"error": "not found"}), 404
        return jsonify(result)

    @app.route("/api/agriproduction/delivery", methods=["POST"])
    def api_agriproduction_delivery():
        from core.agriproduction import AgriProduction
        data = request.get_json()
        if not data or not data.get("order_id"):
            return jsonify({"error": "order_id required"}), 400
        ap = AgriProduction()
        result = ap.create_delivery_note(
            data["order_id"], data.get("client"),
            data.get("client_address"),
            data.get("tva_pct", 5.5))
        return jsonify(result), 201

    @app.route("/api/agriproduction/deliveries", methods=["GET"])
    def api_agriproduction_deliveries():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.list_delivery_notes(
            request.args.get("client"),
            request.args.get("paid", type=bool)))

    @app.route("/api/agriproduction/deliveries/<note_id>/pay", methods=["PUT"])
    def api_agriproduction_delivery_pay(note_id):
        from core.agriproduction import AgriProduction
        data = request.get_json(silent=True) or {}
        ap = AgriProduction()
        result = ap.mark_delivery_paid(note_id, data.get("paid_date"))
        if not result:
            return jsonify({"error": "not found"}), 404
        return jsonify(result)

    @app.route("/api/agriproduction/sales", methods=["GET"])
    def api_agriproduction_sales():
        from core.agriproduction import AgriProduction
        ap = AgriProduction()
        return jsonify(ap.sales_summary())

    # ── Device Catalog ──────────────────────────────────────

    @app.route("/api/devices/stats", methods=["GET"])
    def api_device_stats():
        from core.discovery import device_manager
        return jsonify(device_manager.stats())

    @app.route("/api/devices", methods=["GET"])
    def api_devices_list():
        from core.discovery import device_manager
        devices = device_manager.list_devices(
            status=request.args.get("status"),
            protocol=request.args.get("protocol"),
            space_id=request.args.get("space"),
            device_type=request.args.get("device_type"),
        )
        return jsonify(devices)

    @app.route("/api/devices/<device_id>", methods=["GET"])
    def api_device_get(device_id):
        from core.discovery import device_manager
        d = device_manager.get_device(device_id)
        if not d:
            return jsonify({"error": "device not found"}), 404
        return jsonify(d)

    @app.route("/api/devices", methods=["POST"])
    def api_device_register():
        from core.discovery import device_manager
        data = request.get_json()
        if not data or not data.get("device_id"):
            return jsonify({"error": "device_id required"}), 400
        device = device_manager.register_device(
            device_id=data["device_id"],
            protocol=data.get("protocol", "unknown"),
            fingerprint=data.get("fingerprint", ""),
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", ""),
            device_type=data.get("device_type", "unknown"),
            sensor_type=data.get("sensor_type", ""),
            space_id=data.get("space_id", ""),
            ip_address=data.get("ip_address", ""),
            mac_address=data.get("mac_address", ""),
            signal_strength=data.get("signal_strength", 0),
            battery_level=data.get("battery_level", 100.0),
            meta=data.get("meta"),
        )
        return jsonify(device), 201

    @app.route("/api/devices/<device_id>", methods=["PUT"])
    def api_device_update(device_id):
        from core.discovery import device_manager
        data = request.get_json(silent=True) or {}
        ok = device_manager.update_device(device_id, **data)
        if not ok:
            return jsonify({"error": "update failed"}), 400
        return jsonify({"status": "updated", "device_id": device_id})

    @app.route("/api/devices/<device_id>", methods=["DELETE"])
    def api_device_delete(device_id):
        from core.discovery import device_manager
        ok = device_manager.delete_device(device_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "deleted", "device_id": device_id})

    @app.route("/api/devices/<device_id>/provision", methods=["POST"])
    def api_device_provision(device_id):
        from core.discovery import device_manager
        data = request.get_json(silent=True) or {}
        ok = device_manager.provision(
            device_id,
            space_id=data.get("space_id", ""),
            space_label=data.get("space_label", ""),
            device_type=data.get("device_type"),
        )
        if not ok:
            return jsonify({"error": "provision failed"}), 400
        return jsonify({"status": "provisioned", "device_id": device_id})

    @app.route("/api/devices/<device_id>/activate", methods=["POST"])
    def api_device_activate(device_id):
        from core.discovery import device_manager
        ok = device_manager.activate(device_id)
        if not ok:
            return jsonify({"error": "activate failed"}), 400
        return jsonify({"status": "activated", "device_id": device_id})

    @app.route("/api/devices/<device_id>/retire", methods=["POST"])
    def api_device_retire(device_id):
        from core.discovery import device_manager
        ok = device_manager.retire(device_id)
        if not ok:
            return jsonify({"error": "retire failed"}), 400
        return jsonify({"status": "retired", "device_id": device_id})

    @app.route("/api/devices/scan", methods=["POST"])
    def api_device_scan():
        from core.discovery import device_manager
        data = request.get_json(silent=True) or {}
        timeout = data.get("timeout", 30)
        results = device_manager.scan_all(timeout=timeout)
        return jsonify(results)

    @app.route("/api/devices/<device_id>/fingerprint", methods=["POST"])
    def api_device_fingerprint(device_id):
        from core.discovery import device_manager
        d = device_manager.get_device(device_id)
        if not d:
            return jsonify({"error": "device not found"}), 404
        result = device_manager.fingerprint(
            device_id, d.get("protocol", ""),
            d.get("fingerprint", ""))
        return jsonify(result or {"status": "unknown"})

    # ── Production ───────────────────────────────────────────

    @app.route("/production")
    def production_page():
        return render_template("production.html", title="Production")

    @app.route("/api/production/dashboard")
    def api_production_dashboard():
        from core.production import production_manager
        return jsonify(production_manager.full_dashboard())

    @app.route("/api/production/stats")
    def api_production_stats():
        from core.production import production_manager
        return jsonify(production_manager.stats())

    # Soil Preparation
    @app.route("/api/production/soil", methods=["GET"])
    def api_production_soil_list():
        from core.production import production_manager
        items = production_manager.list_soil_preps(
            space_id=request.args.get("space"),
            status=request.args.get("status"),
        )
        return jsonify(items)

    @app.route("/api/production/soil", methods=["POST"])
    def api_production_soil_create():
        from core.production import production_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        sp = production_manager.create_soil_prep(
            name=data.get("name", "sol"),
            space_id=data.get("space_id", ""),
            sub_zone_id=data.get("sub_zone_id", ""),
            preparation_type=data.get("preparation_type", "labour"),
            area_m2=data.get("area_m2", 0),
            depth_cm=data.get("depth_cm", 0),
            soil_condition=data.get("soil_condition", ""),
            texture=data.get("texture", ""),
            notes=data.get("notes", ""),
            assigned_to=data.get("assigned_to", ""),
            start_date=data.get("start_date", ""),
        )
        return jsonify(sp.to_dict()), 201

    @app.route("/api/production/soil/<prep_id>", methods=["GET"])
    def api_production_soil_get(prep_id):
        from core.production import production_manager
        sp = production_manager.get_soil_prep(prep_id)
        if not sp:
            return jsonify({"error": "not found"}), 404
        return jsonify(sp.to_dict())

    @app.route("/api/production/soil/<prep_id>", methods=["PUT"])
    def api_production_soil_update(prep_id):
        from core.production import production_manager
        data = request.get_json(silent=True) or {}
        sp = production_manager.update_soil_prep(prep_id, **data)
        if not sp:
            return jsonify({"error": "not found"}), 404
        return jsonify(sp.to_dict())

    @app.route("/api/production/soil/<prep_id>/amend", methods=["POST"])
    def api_production_soil_amend(prep_id):
        from core.production import production_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        sp = production_manager.add_soil_amendment(
            prep_id, data.get("amendment_type", "compost"),
            data.get("quantity_kg", 0),
            product_name=data.get("product_name", ""),
            notes=data.get("notes", ""),
        )
        if not sp:
            return jsonify({"error": "not found"}), 404
        return jsonify(sp.to_dict())

    @app.route("/api/production/soil/<prep_id>/activity", methods=["POST"])
    def api_production_soil_activity(prep_id):
        from core.production import production_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        sp = production_manager.add_soil_activity(
            prep_id, data.get("activity", ""),
            details=data.get("details", ""),
            duration_hours=data.get("duration_hours", 0),
        )
        if not sp:
            return jsonify({"error": "not found"}), 404
        return jsonify(sp.to_dict())

    @app.route("/api/production/soil/<prep_id>", methods=["DELETE"])
    def api_production_soil_delete(prep_id):
        from core.production import production_manager
        ok = production_manager.delete_soil_prep(prep_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "deleted"})

    # Planting
    @app.route("/api/production/planting", methods=["GET"])
    def api_production_planting_list():
        from core.production import production_manager
        items = production_manager.list_plantings(
            space_id=request.args.get("space"),
            status=request.args.get("status"),
            product_id=request.args.get("product_id"),
        )
        return jsonify(items)

    @app.route("/api/production/planting", methods=["POST"])
    def api_production_planting_create():
        from core.production import production_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        tp = production_manager.create_planting(
            name=data.get("name", "plantation"),
            space_id=data.get("space_id", ""),
            sub_zone_id=data.get("sub_zone_id", ""),
            product_id=data.get("product_id", ""),
            product_name=data.get("product_name", ""),
            variety=data.get("variety", ""),
            rootstock=data.get("rootstock", ""),
            plant_count=data.get("plant_count", 0),
            spacing_m=data.get("spacing_m", 0),
            spacing_plant=data.get("spacing_plant", 0),
            planting_method=data.get("planting_method", "trou"),
            planting_date=data.get("planting_date", ""),
            notes=data.get("notes", ""),
            assigned_to=data.get("assigned_to", ""),
            stake_type=data.get("stake_type", "aucun"),
            initial_watering_l=data.get("initial_watering_l", 0),
            mulch_type=data.get("mulch_type", "aucun"),
            irrigation_type=data.get("irrigation_type", "aucun"),
            hole_depth_cm=data.get("hole_depth_cm", 0),
            hole_width_cm=data.get("hole_width_cm", 0),
        )
        return jsonify(tp.to_dict()), 201

    @app.route("/api/production/planting/<planting_id>", methods=["GET"])
    def api_production_planting_get(planting_id):
        from core.production import production_manager
        tp = production_manager.get_planting(planting_id)
        if not tp:
            return jsonify({"error": "not found"}), 404
        return jsonify(tp.to_dict())

    @app.route("/api/production/planting/<planting_id>", methods=["PUT"])
    def api_production_planting_update(planting_id):
        from core.production import production_manager
        data = request.get_json(silent=True) or {}
        tp = production_manager.update_planting(planting_id, **data)
        if not tp:
            return jsonify({"error": "not found"}), 404
        return jsonify(tp.to_dict())

    @app.route("/api/production/planting/<planting_id>", methods=["DELETE"])
    def api_production_planting_delete(planting_id):
        from core.production import production_manager
        ok = production_manager.delete_planting(planting_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "deleted"})

    # Production Plans
    @app.route("/api/production/plans", methods=["GET"])
    def api_production_plans_list():
        from core.production import production_manager
        items = production_manager.list_plans(
            space_id=request.args.get("space"),
            status=request.args.get("status"),
            season=request.args.get("season"),
            year=request.args.get("year", type=int),
        )
        return jsonify(items)

    @app.route("/api/production/plans", methods=["POST"])
    def api_production_plans_create():
        from core.production import production_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        plan = production_manager.create_plan(
            name=data.get("name", "plan"),
            space_id=data.get("space_id", ""),
            sub_zone_id=data.get("sub_zone_id", ""),
            product_id=data.get("product_id", ""),
            product_name=data.get("product_name", ""),
            season=data.get("season", ""),
            year=data.get("year"),
            estimated_yield_kg=data.get("estimated_yield_kg", 0),
            start_date=data.get("start_date", ""),
            estimated_end_date=data.get("estimated_end_date", ""),
            notes=data.get("notes", ""),
        )
        return jsonify(plan.to_dict()), 201

    @app.route("/api/production/plans/<plan_id>", methods=["GET"])
    def api_production_plans_get(plan_id):
        from core.production import production_manager
        plan = production_manager.get_plan(plan_id)
        if not plan:
            return jsonify({"error": "not found"}), 404
        return jsonify(plan.to_dict())

    @app.route("/api/production/plans/<plan_id>", methods=["PUT"])
    def api_production_plans_update(plan_id):
        from core.production import production_manager
        data = request.get_json(silent=True) or {}
        plan = production_manager.update_plan(plan_id, **data)
        if not plan:
            return jsonify({"error": "not found"}), 404
        return jsonify(plan.to_dict())

    @app.route("/api/production/plans/<plan_id>", methods=["DELETE"])
    def api_production_plans_delete(plan_id):
        from core.production import production_manager
        ok = production_manager.delete_plan(plan_id)
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "deleted"})

    @app.route("/api/production/plans/<plan_id>/link-soil", methods=["POST"])
    def api_production_plans_link_soil(plan_id):
        from core.production import production_manager
        data = request.get_json(silent=True) or {}
        soil_prep_id = data.get("soil_prep_id", "")
        if not soil_prep_id:
            return jsonify({"error": "soil_prep_id required"}), 400
        ok = production_manager.link_soil_prep_to_plan(plan_id, soil_prep_id)
        if not ok:
            return jsonify({"error": "link failed"}), 400
        return jsonify({"status": "linked"})

    # ── Production Calendar ─────────────────────────────────

    @app.route("/planning")
    def planning_page():
        return render_template("planning.html", title="Planning de Production")

    @app.route("/api/production/calendar")
    def api_production_calendar():
        from core.production import production_manager
        product = request.args.get("product", "")
        zone = request.args.get("zone", "")
        sub_zone = request.args.get("sub_zone", "")
        variety = request.args.get("variety", "")
        type_filter = request.args.get("type", "")  # soil, planting, plan

        soils = production_manager.list_soil_preps() if type_filter in ("", "soil") else []
        plantings = production_manager.list_plantings() if type_filter in ("", "planting") else []
        plans = production_manager.list_plans() if type_filter in ("", "plan") else []

        events = []

        for s in soils:
            if zone and s.get("space_id") != zone:
                continue
            if sub_zone and s.get("sub_zone_id") != sub_zone:
                continue
            start = (s.get("start_date") or s.get("created_at", ""))[:10]
            end = (s.get("completion_date") or start)[:10]
            events.append({
                "id": s["id"], "type": "soil",
                "title": s.get("name", ""),
                "subtitle": s.get("preparation_type", ""),
                "start": start, "end": end,
                "zone": s.get("space_id", ""), "sub_zone": s.get("sub_zone_id", ""),
                "product": "", "variety": "",
                "area_m2": s.get("area_m2", 0),
                "status": s.get("status", ""),
                "color": "#2e7d32",
            })

        for p in plantings:
            if zone and p.get("space_id") != zone:
                continue
            if sub_zone and p.get("sub_zone_id") != sub_zone:
                continue
            if product and p.get("product_id") != product:
                continue
            if variety and p.get("variety") != variety:
                continue
            d = (p.get("planting_date") or p.get("created_at", ""))[:10]
            events.append({
                "id": p["id"], "type": "planting",
                "title": p.get("name", ""),
                "subtitle": p.get("product_name") or p.get("product_id", ""),
                "start": d, "end": d,
                "zone": p.get("space_id", ""), "sub_zone": p.get("sub_zone_id", ""),
                "product": p.get("product_id", ""),
                "variety": p.get("variety", ""),
                "plant_count": p.get("plant_count", 0),
                "method": p.get("planting_method", ""),
                "status": p.get("status", ""),
                "color": "#7cb342",
            })

        for pl in plans:
            if zone and pl.get("space_id") != zone:
                continue
            if sub_zone and pl.get("sub_zone_id") != sub_zone:
                continue
            if product and pl.get("product_id") != product:
                continue
            start = (pl.get("start_date") or pl.get("created_at", ""))[:10]
            end = (pl.get("estimated_end_date") or start)[:10]
            events.append({
                "id": pl["id"], "type": "plan",
                "title": pl.get("name", ""),
                "subtitle": f"{pl.get('season','')} {pl.get('year','')}",
                "start": start, "end": end,
                "zone": pl.get("space_id", ""), "sub_zone": pl.get("sub_zone_id", ""),
                "product": pl.get("product_id", ""),
                "variety": "",
                "yield_kg": pl.get("estimated_yield_kg", 0),
                "status": pl.get("status", ""),
                "color": "#f9a825",
            })

        # Facets for filters
        facets = {
            "zones": sorted(set(e["zone"] for e in events if e["zone"])),
            "sub_zones": sorted(set(e["sub_zone"] for e in events if e["sub_zone"])),
            "products": sorted(set(e["product"] for e in events if e["product"])),
            "varieties": sorted(set(e["variety"] for e in events if e["variety"])),
        }

        return jsonify({"events": events, "facets": facets})

    @app.route("/api/production/plans/<plan_id>/link-planting", methods=["POST"])
    def api_production_plans_link_planting(plan_id):
        from core.production import production_manager
        data = request.get_json(silent=True) or {}
        planting_id = data.get("planting_id", "")
        if not planting_id:
            return jsonify({"error": "planting_id required"}), 400
        ok = production_manager.link_planting_to_plan(plan_id, planting_id)
        if not ok:
            return jsonify({"error": "link failed"}), 400
        return jsonify({"status": "linked"})

    # ── RL Controller ──────────────────────────────────────

    @app.route("/api/rl/stats", methods=["GET"])
    def api_rl_stats():
        from core.rl_controller import RLController
        zone = request.args.get("zone", "serre_a")
        rl = RLController(zone)
        return jsonify(rl.stats())

    @app.route("/api/rl/step", methods=["POST"])
    def api_rl_step():
        from core.rl_controller import RLController, ACTION_LABELS
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        zone = data.get("zone", "serre_a")
        moisture = data.get("moisture")
        temp = data.get("temp")
        if moisture is None or temp is None:
            return jsonify({"error": "moisture and temp required"}), 400
        rl = RLController(zone)
        hour = data.get("hour", datetime.now().hour)
        action = rl.choose_action(moisture, temp, hour)
        best = rl.get_best_action(moisture, temp, hour)
        return jsonify({
            "action": int(action),
            "label": ACTION_LABELS[action],
            "epsilon": rl.epsilon,
            "best": best,
            "zone": zone,
        })

    @app.route("/api/rl/history", methods=["GET"])
    def api_rl_history():
        from core.rl_controller import RLController
        zone = request.args.get("zone", "serre_a")
        limit = request.args.get("limit", 50, type=int)
        rl = RLController(zone)
        return jsonify(rl.history(limit=limit))

    @app.route("/api/rl/best", methods=["GET"])
    def api_rl_best():
        from core.rl_controller import RLController
        zone = request.args.get("zone", "serre_a")
        moisture = request.args.get("moisture", type=float)
        temp = request.args.get("temp", type=float)
        if moisture is None or temp is None:
            return jsonify({"error": "moisture and temp params required"}), 400
        hour = request.args.get("hour", datetime.now().hour, type=int)
        rl = RLController(zone)
        return jsonify(rl.get_best_action(moisture, temp, hour))

    # ── Edge Inference ─────────────────────────────────────

    @app.route("/api/ml/edge/stats", methods=["GET"])
    def api_edge_stats():
        from agent.edge_inference import EdgeInferenceEngine
        from core.config import PixelOSConfig
        from core.mqtt import PixelOSMQTT
        cfg = PixelOSConfig()
        mqtt = PixelOSMQTT(broker=cfg.get("mqtt.broker", "localhost"),
                            port=cfg.get("mqtt.port", 1883),
                            client_id="pixelos-web-edge")
        mqtt.connect()
        engine = EdgeInferenceEngine(mqtt)
        engine.load_model()
        return jsonify(engine.stats())

    @app.route("/api/ml/edge/predict", methods=["POST"])
    def api_edge_predict():
        from agent.edge_inference import EdgeInferenceEngine
        from core.config import PixelOSConfig
        from core.mqtt import PixelOSMQTT
        data = request.get_json()
        if not data:
            return jsonify({"error": "body required"}), 400
        cfg = PixelOSConfig()
        mqtt = PixelOSMQTT(broker=cfg.get("mqtt.broker", "localhost"),
                            port=cfg.get("mqtt.port", 1883),
                            client_id="pixelos-web-edge")
        mqtt.connect()
        engine = EdgeInferenceEngine(mqtt)
        engine.load_model()
        space_id = data.pop("space_id", "serre_a")
        result = engine.predict_and_act(space_id, data)
        return jsonify(result)

    # ── Training Scheduler ─────────────────────────────────

    @app.route("/api/ml/scheduler/check", methods=["GET"])
    def api_scheduler_check():
        from agent.training_scheduler import TrainingScheduler
        from core.config import PixelOSConfig
        from core.mqtt import PixelOSMQTT
        cfg = PixelOSConfig()
        mqtt = PixelOSMQTT(broker=cfg.get("mqtt.broker", "localhost"),
                            port=cfg.get("mqtt.port", 1883),
                            client_id="pixelos-web-scheduler")
        mqtt.connect()
        ts = TrainingScheduler(mqtt)
        reason = ts.should_train()
        return jsonify({"should_train": reason is not None, "reason": reason, "stats": ts.stats()})

    @app.route("/api/ml/scheduler/run", methods=["POST"])
    def api_scheduler_run():
        from agent.training_scheduler import TrainingScheduler
        from core.config import PixelOSConfig
        from core.mqtt import PixelOSMQTT
        data = request.get_json(silent=True) or {}
        cfg = PixelOSConfig()
        mqtt = PixelOSMQTT(broker=cfg.get("mqtt.broker", "localhost"),
                            port=cfg.get("mqtt.port", 1883),
                            client_id="pixelos-web-scheduler")
        mqtt.connect()
        ts = TrainingScheduler(mqtt)
        if data.get("check_first", True):
            reason = ts.should_train()
            if not reason and not data.get("force"):
                return jsonify({"status": "skipped", "reason": "pas necessaire"})
        result = ts.run_training(force=data.get("force", False))
        return jsonify(result)

    @app.route("/api/ml/scheduler/stats", methods=["GET"])
    def api_scheduler_stats():
        from agent.training_scheduler import TrainingScheduler
        from core.config import PixelOSConfig
        from core.mqtt import PixelOSMQTT
        cfg = PixelOSConfig()
        mqtt = PixelOSMQTT(broker=cfg.get("mqtt.broker", "localhost"),
                            port=cfg.get("mqtt.port", 1883),
                            client_id="pixelos-web-scheduler")
        mqtt.connect()
        ts = TrainingScheduler(mqtt)
        return jsonify(ts.stats())

    # ── Pages manquantes (modules existants sans template) ──

    @app.route("/lab")
    def lab_page():
        return render_template("lab.html", title="Laboratoire")

    @app.route("/omics")
    def omics_page():
        return render_template("omics.html", title="Bioinformatique")

    @app.route("/ontology")
    def ontology_page():
        return render_template("ontology.html", title="Ontologie Végétale")

    @app.route("/vision")
    def vision_page():
        return render_template("vision.html", title="Vision par ordinateur")

    @app.route("/cultivation")
    def cultivation_page():
        return render_template("cultivation.html", title="Monitoring Cultural")

    @app.route("/rl")
    def rl_page():
        return render_template("rl.html", title="RL Controller")

    @app.route("/devices")
    def devices_page():
        return render_template("devices.html", title="Périphériques")

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
