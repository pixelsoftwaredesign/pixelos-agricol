#!/usr/bin/env python3
"""
PixelOS CLI - Interface de gestion complète du système agricole.
Usage: pixelos <commande> [options]
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Ajouter src au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import PixelOSConfig
from core.mqtt import PixelOSMQTT

config = PixelOSConfig()


def cmd_status(args):
    """État global du système."""
    from core.mqtt import PixelOSMQTT

    print("╔══════════════════════════════════════════╗")
    print("║        PixelOS - État du système        ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # MQTT
    mqtt = PixelOSMQTT()
    try:
        mqtt.connect()
        mqtt_status = "✅ Connecté" if mqtt.connected else "❌ Déconnecté"
    except:
        mqtt_status = "❌ Erreur connexion"
    print(f"  MQTT Broker : {mqtt_status}")

    # Base de données
    print(f"  MySQL       : {'✅ OK' if _check_mysql() else '❌ Erreur'}")
    print(f"  MongoDB     : {'✅ OK' if _check_mongodb() else '❌ Erreur'}")

    # Backend
    print(f"  API Backend : {'✅ OK' if _check_backend() else '❌ Erreur'}")

    # Nœuds
    print()
    online = sum(1 for n in config.nodes.values() if _ping_node(n))
    total = len(config.nodes)
    print(f"  Nœuds       : {online}/{total} en ligne")

    if args.node:
        n = config.get_node(args.node)
        if n:
            print(f"\n  Détail {args.node}:")
            print(f"    Type   : {n['type']}")
            print(f"    Adresse: {n['addr']}")
            print(f"    Loc.   : {n.get('location', 'N/A')}")
            print(f"    Com.   : {n['communication']}")


def cmd_node(args):
    """Gestion des nœuds."""
    if args.action == "list":
        print(f"{'ID':<20} {'Type':<15} {'Adr':<5} {'Location':<20} {'Com':<8} {'Status'}")
        print("-" * 90)
        for n in config.nodes.values():
            online = _ping_node(n)
            status = "🟢" if online else "🔴"
            print(f"{n['id']:<20} {n['type']:<15} {n['addr']:<5} "
                  f"{n.get('location','?'):<20} {n['communication']:<8} {status}")

    elif args.action == "config":
        n = config.get_node(args.node_id)
        if not n:
            print(f"❌ Nœud {args.node_id} introuvable")
            return
        print(json.dumps(n, indent=2, ensure_ascii=False))


def cmd_irrigate(args):
    """Gestion de l'irrigation."""
    mqtt = PixelOSMQTT()
    mqtt.connect()

    if args.action == "status":
        print("État irrigation par zone :")
        print("-" * 50)
        for n in config.get_nodes_by_type("capteur_sol"):
            irr = n.get("irrigation", {})
            seuil = irr.get("seuil_secheresse", "N/A")
            valve = irr.get("valve_addr", "N/A")
            print(f"  {n['id']:<15} seuil={seuil:<5} vanne={valve}")

    elif args.action in ("open", "close"):
        cmd = "OUVRIR" if args.action == "open" else "FERMER"
        for n in config.nodes.values():
            if n["type"] == "vanne" and (args.zone in n["id"] or args.zone == "all"):
                topic = f"agricol/commande/vanne/{n['id']}"
                mqtt.publish(topic, {"cmd": cmd})
                print(f"  → {topic}: {cmd}")
        mqtt.disconnect()


def cmd_firmware(args):
    """Gestion des firmwares."""
    from core.ota import FirmwareOTA

    ota = FirmwareOTA()

    if args.action == "list":
        versions = ota.list_versions()
        if not versions:
            print("Aucun firmware disponible")
            return
        for node_type, vers in versions.items():
            print(f"\n{node_type}:")
            for v in vers:
                print(f"  └─ {v['variant']} ({v['modified']})")
                for f in v['files']:
                    print(f"      └─ {Path(f).name}")

    elif args.action == "build":
        fw_path = ota.build(args.type)
        print(f"✅ Firmware compilé: {fw_path}")


def cmd_monitor(args):
    """Monitoring du système."""
    if args.action == "health":
        checks = {
            "mqtt": _check_mqtt(),
            "mysql": _check_mysql(),
            "mongodb": _check_mongodb(),
            "backend": _check_backend(),
            "disk": _check_disk(),
            "memory": _check_memory(),
        }
        print(f"{'Composant':<15} {'Status':<10} {'Détail'}")
        print("-" * 60)
        for comp, (ok, detail) in checks.items():
            icon = "✅" if ok else "❌"
            print(f"{comp:<15} {icon:<10} {detail}")

    elif args.action == "alerts":
        alerts = config.alerts
        if not alerts:
            print("Aucune règle d'alerte configurée")
            return
        print(f"{'Alerte':<30} {'Severité':<10} {'Condition'}")
        print("-" * 80)
        for a in alerts:
            sev = a.get("severity", "info")
            print(f"{a['name']:<30} {sev:<10} {a.get('condition','')[:50]}")


def cmd_backup(args):
    """Backup du système."""
    from core.backup import BackupManager

    bk = BackupManager(path=config.get("backup.path", "/var/backups/pixelos"))

    if args.action == "create" or args.action is None:
        path = bk.create()
        print(f"✅ Backup créé: {path}")

    elif args.action == "list":
        backups = bk.list_backups()
        if not backups:
            print("Aucun backup")
            return
        print(f"{'Date':<25} {'Taille':<10} {'Path'}")
        print("-" * 70)
        for b in backups:
            print(f"{b['date']:<25} {b['size']:<10} {b['path']}")

    elif args.action == "restore":
        bk.restore(args.backup_id if args.backup_id != "latest" else None)


def cmd_zone(args):
    """Découverte et gestion des zones / capteurs."""
    from core.discovery import AggregateScanner
    from core.provisioning import ZoneManager
    from core.config import PixelOSConfig

    zm = ZoneManager()

    if args.action == "list":
        zones = zm.list_zones()
        if not zones:
            print("Aucune zone configurée")
            return
        print(f"{'Zone':<25} {'Nœuds':<8} {'Types'}")
        print("-" * 60)
        for z in zones:
            types = ", ".join(set(n["type"] for n in z["nodes"]))
            print(f"{z['location']:<25} {z['count']:<8} {types}")

    elif args.action == "scan":
        print("🔍 Scan en cours (Wi-Fi + BLE + RS485)...")
        scanner = AggregateScanner()
        results = scanner.scan_all(timeout=args.timeout or 30)
        total = len(results["total"])

        print(f"\n📡 Découvertes :")
        print(f"   Wi-Fi : {len(results['wifi'])} appareils")
        print(f"   BLE   : {len(results['ble'])} appareils")
        print(f"   RS485 : {len(results['rs485'])} nœuds")
        print(f"   Total : {total} capteurs détectés\n")

        if total == 0:
            print("   Aucun nouveau capteur PixelOS détecté")
            print("   Vérifie que les ESP32 diffusent bien un beacon PIXELOS-...")
            return

        # Nouveaux vs existants
        new_nodes = zm.detect_new(results["total"])
        print(f"{'Adr/MAC':<20} {'Type':<12} {'Com':<8} {'Nom':<20} {'Status'}")
        print("-" * 80)
        for d in results["total"]:
            node_id = d.get("nom") or f"{d['type']}_{d.get('addr', d.get('mac', '?'))}"
            exists = node_id in config.nodes
            status = "🟢 Exist" if exists else "🟡 Nouveau"
            com = d.get("communication", d.get("source", "?"))
            addr = str(d.get("addr", d.get("mac", d.get("rssi", "?"))))
            print(f"{addr:<20} {d['type']:<12} {com:<8} {node_id:<20} {status}")

        if new_nodes and not args.dry_run:
            print(f"\n📝 {len(new_nodes)} nouveau(x) capteur(s) détecté(s)")
            yn = input("   Enregistrer dans la config ? [Y/n] ").strip().lower()
            if yn in ("", "y", "yes", "o", "oui"):
                zone = args.zone or input("   Zone (location) : ").strip() or "Auto-détecté"
                res = zm.register_batch(new_nodes, zone)
                print(f"   ✅ {len(res['registered'])} enregistré(s)")
                if res["errors"]:
                    for e in res["errors"]:
                        print(f"   ❌ {e['node']}: {e['error']}")

    elif args.action == "detect":
        print("⚡ Détection rapide des nouveaux capteurs...")
        scanner = AggregateScanner()
        results = scanner.scan_all(timeout=args.timeout or 15)
        new_nodes = zm.detect_new(results["total"])

        if not new_nodes:
            print("   Aucun nouveau capteur détecté")
            return

        print(f"\n{'Nom':<20} {'Type':<12} {'Source':<8} {'Actions'}")
        print("-" * 60)
        for n in new_nodes:
            print(f"{n['id']:<20} {n['type']:<12} {n['source']:<8} "
                  f"→ pixelos zone register {n['id']}")

    elif args.action == "register":
        # Register a specific node by attributes
        node_def = {
            "id": args.name,
            "addr": args.addr or 0,
            "type": args.type or "capteur_sol",
            "location": args.zone or args.location or "Auto-détecté",
            "communication": args.com or "wifi",
        }
        ok = zm.register(node_def, args.zone)
        print(f"{'✅' if ok else '❌'} Nœud {args.name} {'enregistré' if ok else 'déjà existant'}")

    elif args.action == "assign":
        ok = zm.assign_to_zone(args.node_id, args.zone)
        print(f"{'✅' if ok else '❌'} Nœud {args.node_id} → {args.zone}")

    elif args.action == "remove":
        ok = zm.remove(args.node_id)
        print(f"{'✅' if ok else '❌'} Nœud {args.node_id} retiré")

    elif args.action == "auto":
        """Mode auto : scan + enregistrement automatique."""
        import time

        print("🤖 Mode auto-provisioning actif (Ctrl+C pour arrêter)")
        scanner = AggregateScanner()
        zm = ZoneManager()
        interval = args.interval or 60

        try:
            while True:
                results = scanner.scan_all(timeout=max(10, interval // 2))
                new_nodes = zm.detect_new(results["total"])

                if new_nodes:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                          f"{len(new_nodes)} nouveau(x) capteur(s) !")
                    res = zm.register_batch(new_nodes, args.zone or "Auto-provisioning")
                    print(f"   ✅ {len(res['registered'])} enregistré(s)")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"Scan: {len(results['total'])} appareils, 0 nouveau")

                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n⏹️  Auto-provisioning arrêté")

    elif args.action == "beacon":
        """Diffuse un beacon BLE depuis le serveur (test)."""
        from core.discovery import DiscoveryProtocol
        ssid = DiscoveryProtocol.make_wifi_ap(args.type or "SOL", args.name or "test")
        print(f"📡 SSID beacon : {ssid}")
        print(f"📡 BLE UUID    : {DiscoveryProtocol.PIXELOS_BLE_UUID}")

        # Créer un AP Wi-Fi temporaire
        if args.create_ap:
            import subprocess
            try:
                subprocess.run([
                    "nmcli", "device", "wifi", "hotspot",
                    "ssid", ssid, "password", "pixelos2026"
                ], timeout=10)
                print(f"✅ Point d'accès créé: {ssid}")
            except Exception as e:
                print(f"❌ Échec création AP: {e}")


def cmd_predict(args):
    """Moteur de prédiction IA."""
    from core.predictor import PredictorCLI
    PredictorCLI.handle(args)


def cmd_config(args):
    """Gestion de la configuration."""
    if args.action == "show":
        print(config.to_json())

    elif args.action == "set" and args.key and args.value:
        config.set(args.key, args.value)
        print(f"✅ {args.key} = {args.value}")


# ─── Utilitaires ───

def _check_mqtt() -> tuple[bool, str]:
    try:
        m = PixelOSMQTT()
        m.connect()
        ok = m.connected
        m.disconnect()
        return ok, "Connecté" if ok else "Timeout"
    except Exception as e:
        return False, str(e)

def _check_mysql() -> tuple[bool, str]:
    try:
        import mysql.connector
        c = mysql.connector.connect(
            host=config.get("database.mysql.host", "localhost"),
            port=config.get("database.mysql.port", 3306),
            user=config.get("database.mysql.user", "agricol"),
            database=config.get("database.mysql.database", "agricol"),
        )
        c.close()
        return True, "Connecté"
    except Exception as e:
        return False, str(e)

def _check_mongodb() -> tuple[bool, str]:
    try:
        from pymongo import MongoClient
        client = MongoClient(config.get("database.mongodb.uri",
                                         "mongodb://localhost:27017/"))
        client.admin.command("ping")
        return True, "Connecté"
    except Exception as e:
        return False, str(e)

def _check_backend() -> tuple[bool, str]:
    import requests
    try:
        r = requests.get(f"{config.get('backend.api_url')}/health", timeout=5)
        return r.ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

def _check_disk() -> tuple[bool, str]:
    import shutil
    usage = shutil.disk_usage("/")
    pct = usage.used / usage.total * 100
    return pct < 90, f"{pct:.0f}% utilisé"

def _check_memory() -> tuple[bool, str]:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.percent < 90, f"{mem.percent:.0f}% utilisé"
    except:
        return True, "N/A"

def _ping_node(node: dict) -> bool:
    """Vérification simple de l'état du nœud."""
    return True  # TODO: implémenter heartbeat MQTT


def main():
    parser = argparse.ArgumentParser(
        description="PixelOS - Système de Gestion Agricole Connecté",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version="PixelOS 2.0")

    sub = parser.add_subparsers(dest="command")

    # status
    p = sub.add_parser("status", help="État du système")
    p.add_argument("--node", help="Détail d'un nœud spécifique")
    p.set_defaults(func=cmd_status)

    # node
    p = sub.add_parser("node", help="Gestion des nœuds")
    p.add_argument("action", choices=["list", "config"])
    p.add_argument("node_id", nargs="?")
    p.set_defaults(func=cmd_node)

    # irrigate
    p = sub.add_parser("irrigate", help="Contrôle irrigation")
    p.add_argument("action", choices=["status", "open", "close"])
    p.add_argument("zone", nargs="?", default="all")
    p.set_defaults(func=cmd_irrigate)

    # firmware
    p = sub.add_parser("firmware", help="Gestion firmware OTA")
    p.add_argument("action", choices=["list", "build", "flash"])
    p.add_argument("--type", help="Type de nœud (sensor_node, valve_node...)")
    p.set_defaults(func=cmd_firmware)

    # monitor
    p = sub.add_parser("monitor", help="Monitoring")
    p.add_argument("action", choices=["health", "alerts"])
    p.set_defaults(func=cmd_monitor)

    # backup
    p = sub.add_parser("backup", help="Backup/Restore")
    p.add_argument("action", choices=["create", "list", "restore"], nargs="?")
    p.add_argument("backup_id", nargs="?")
    p.set_defaults(func=cmd_backup)

    # predict
    p = sub.add_parser("predict", help="Prédiction IA (irrigation, anomalies)")
    p.add_argument("action", choices=["train", "predict", "stats", "anomaly"])
    p.add_argument("--days", type=int, default=30, help="Jours d'historique")
    p.add_argument("--zone", default="sol_serre", help="Zone à entraîner")
    p.add_argument("--humidity", type=float, help="Humidité sol actuelle")
    p.add_argument("--temp", type=float, help="Température actuelle")
    p.add_argument("--hum", type=float, help="Humidité air actuelle")
    p.add_argument("--pression", type=float, help="Pression atmosphérique")
    p.add_argument("--debit", type=float, help="Débit actuel L/min")
    p.set_defaults(func=cmd_predict)

    # zone
    p = sub.add_parser("zone", help="Découverte et gestion des zones/capteurs")
    p.add_argument("action", choices=["list", "scan", "detect", "register",
                                      "assign", "remove", "auto", "beacon"])
    p.add_argument("--zone", "-z", help="Nom de zone (location)")
    p.add_argument("--name", "-n", help="Nom du nœud")
    p.add_argument("--type", "-t", help="Type (sol, vanne, meteo, debit, pir)")
    p.add_argument("--addr", "-a", type=int, help="Adresse Modbus")
    p.add_argument("--com", "-c", help="Communication (wifi, ble, rs485)")
    p.add_argument("--node-id", help="ID du nœud")
    p.add_argument("--timeout", type=int, default=15, help="Timeout scan (s)")
    p.add_argument("--interval", type=int, default=60,
                   help="Intervalle auto-provisioning (s)")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan sans enregistrer")
    p.add_argument("--create-ap", action="store_true",
                   help="Créer un point d'accès Wi-Fi beacon")
    p.set_defaults(func=cmd_zone)

    # config
    p = sub.add_parser("config", help="Configuration")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_config)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
