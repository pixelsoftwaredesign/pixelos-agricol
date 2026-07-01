#!/usr/bin/env python3
"""
PixelOS CLI - Interface de gestion complète du système agricole.
Usage: pixelos <commande> [options]
"""

import sys
import json
import shutil
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
    tsdb_ok, tsdb_msg = _check_tsdb()
    print(f"  MongoDB     : {'✅ OK' if _check_mongodb() else '❌ Erreur'}")
    print(f"  TimescaleDB : {'✅ OK' if tsdb_ok else '⚠️  ' + tsdb_msg}")
 
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


def cmd_device(args):
    """Catalogue et découverte de dispositifs IoT."""
    from core.discovery import device_manager as dm

    if args.action == "list":
        devices = dm.list_devices(
            status=args.status, protocol=args.protocol,
            space_id=args.space, device_type=args.device_type)
        if args.json:
            print(json.dumps(devices, indent=2, ensure_ascii=False, default=str))
            return
        if not devices:
            print("  Aucun dispositif trouvé")
            return
        print(f"\n  Dispositifs ({len(devices)})")
        for d in devices:
            lseen = d.get("last_seen", "")[:16] if d.get("last_seen") else "-"
            print(f"  {d['device_id']:30} {d.get('protocol','?'):6} "
                  f"{d.get('device_type','?'):16} {d.get('status','?'):14} {lseen}")

    elif args.action == "show":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        d = dm.get_device(args.device_id)
        if args.json:
            print(json.dumps(d, indent=2, ensure_ascii=False, default=str))
            return
        if not d:
            print(f"  Dispositif '{args.device_id}' introuvable")
            return
        print(f"\n  Device: {d['device_id']}")
        for k, v in d.items():
            print(f"  | {k}: {v}")

    elif args.action == "register":
        meta = {}
        if args.meta:
            try:
                meta = json.loads(args.meta)
            except json.JSONDecodeError:
                print("  Erreur: meta doit être du JSON valide")
                return
        if args.space:
            meta["space_label"] = args.space
        device = dm.register_device(
            device_id=args.device_id or f"dev-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            protocol=args.protocol or "unknown",
            fingerprint=args.fingerprint or "",
            manufacturer=args.manufacturer or "",
            model=args.model or "",
            device_type=args.device_type or "unknown",
            sensor_type=args.sensor_type or "",
            space_id=args.space or "",
            ip_address=args.ip or "",
            mac_address=args.mac or "",
            signal_strength=args.signal,
            battery_level=args.battery,
            meta=meta,
        )
        if args.json:
            print(json.dumps(device, indent=2, ensure_ascii=False, default=str))
            return
        print(f"  Device enregistré: {device['device_id']} ({device['protocol']})")

    elif args.action == "update":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        updates = {}
        for k in ("protocol", "fingerprint", "manufacturer", "model",
                   "device_type", "sensor_type", "space", "ip", "mac",
                   "signal", "battery"):
            v = getattr(args, k, None)
            if v is not None:
                updates[k] = v
        ok = dm.update_device(args.device_id, **updates)
        print(f"  {'Mis à jour' if ok else 'Échec'}: {args.device_id}")

    elif args.action == "delete":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        ok = dm.delete_device(args.device_id)
        print(f"  {'Supprimé' if ok else 'Échec'}: {args.device_id}")

    elif args.action == "provision":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        ok = dm.provision(args.device_id, space_id=args.space or "",
                          space_label=args.space or "",
                          device_type=args.device_type)
        print(f"  {'Provisionné' if ok else 'Échec'}: {args.device_id}")

    elif args.action == "activate":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        ok = dm.activate(args.device_id)
        print(f"  {'Activé' if ok else 'Échec'}: {args.device_id}")

    elif args.action == "retire":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        ok = dm.retire(args.device_id)
        print(f"  {'Retiré' if ok else 'Échec'}: {args.device_id}")

    elif args.action == "scan-wifi":
        print(f"  Scan Wi-Fi...")
        devices = dm.scan_wifi(timeout=args.timeout)
        if args.json:
            print(json.dumps(devices, indent=2, ensure_ascii=False, default=str))
            return
        print(f"  {len(devices)} dispositifs Wi-Fi trouvés")
        for d in devices:
            print(f"  {d['device_id']:30} {d.get('ip_address','?'):15}")

    elif args.action == "scan-ble":
        print(f"  Scan BLE...")
        devices = dm.scan_ble(timeout=args.timeout)
        if args.json:
            print(json.dumps(devices, indent=2, ensure_ascii=False, default=str))
            return
        print(f"  {len(devices)} dispositifs BLE trouvés")
        for d in devices:
            print(f"  {d['device_id']:30} {d.get('mac_address','?'):17} {d.get('fingerprint','')}")

    elif args.action == "scan-all":
        print(f"  Scan multi-protocole...")
        results = dm.scan_all(timeout=args.timeout)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
            return
        print(f"  Wi-Fi: {len(results['wifi'])}  BLE: {len(results['ble'])}  "
              f"Modbus: {len(results['modbus'])}  Nouveaux: {results['total_new']}")

    elif args.action == "fingerprint":
        if not args.device_id:
            print("  Erreur: device_id requis")
            return
        d = dm.get_device(args.device_id)
        if not d:
            print(f"  Device '{args.device_id}' introuvable")
            return
        result = dm.fingerprint(args.device_id, d.get("protocol", ""),
                                args.fingerprint or d.get("fingerprint", ""))
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return
        if result:
            print(f"  Fingerprint: {result['device_type']} ({result['manufacturer']})")
        else:
            print(f"  Aucun fingerprint trouvé pour {args.device_id}")

    elif args.action == "stats":
        s = dm.stats()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Device Catalog Stats")
        for k, v in s.items():
            print(f"  | {k}: {v}")


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
            "timescaledb": _check_tsdb(),
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


def cmd_plante(args):
    """Base de donnees agronomique des plantes."""
    from core.plantes_db import PlantesDB
    db = PlantesDB()

    if args.action == "list":
        rows = db.list_plantes(args.categorie, args.cycle)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        print(f"\n{'ID':<4} {'Nom':<25} {'Scientifique':<30} {'Categorie':<20} {'Cycle':<10}")
        print("-"*90)
        for r in rows:
            print(f"{r['id']:<4} {r['nom_commun']:<25} {r['nom_scientifique']:<30} {r['categorie']:<20} {r['cycle_vie']:<10}")

    elif args.action == "search":
        rows = db.search(args.query)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        if not rows:
            print(f"Aucune plante trouvee pour '{args.query}'")
            return
        print(f"\n{len(rows)} resultat(s) pour '{args.query}':")
        for r in rows:
            print(f"  [{r['id']}] {r['nom_commun']} ({r['nom_scientifique']}) - {r['categorie']}")
            if r.get('famille'):
                print(f"       Famille: {r['famille']}, Cycle: {r['cycle_vie']}")

    elif args.action == "info":
        row = db.get_plante(args.query)
        if not row:
            print(f"Plante non trouvee: {args.query}")
            return
        if args.json:
            print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
            return
        print(f"\n=== {row['nom_commun']} ({row['nom_scientifique']}) ===")
        print(f"  Categorie : {row['categorie']}")
        print(f"  Famille   : {row.get('famille', 'N/A')}")
        print(f"  Cycle     : {row['cycle_vie']}")
        print(f"  Desc      : {row.get('description', '')}")

        vars = row.get('varietes', [])
        if vars:
            print(f"\n  Varietes ({len(vars)}) :")
            for v in vars:
                print(f"    - {v['nom']} (eau: {v['besoin_eau']}, rendement: {v.get('rendement_estime','N/A')})")

        cals = row.get('calendriers', [])
        if cals:
            print(f"\n  Calendrier :")
            for c in cals:
                print(f"    Semis: {c.get('mois_semis_debut','?')}-{c.get('mois_semis_fin','?')}, Recolte: {c.get('mois_recolte_debut','?')}-{c.get('mois_recolte_fin','?')}, Cycle: {c.get('duree_cycle_jours','?')}j")

        mal = row.get('maladies', [])
        if mal:
            print(f"\n  Maladies ({len(mal)}) :")
            for m in mal:
                print(f"    - {m['nom']} ({m['type_agent']})")

    elif args.action == "categorie":
        rows = db.list_categories()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        print(f"\n{'ID':<4} {'Categorie':<30} {'Plantes':<8}")
        print("-"*45)
        for r in rows:
            print(f"{r['id']:<4} {r['nom']:<30} {r.get('nb_plantes', 0):<8}")

    elif args.action == "maladies":
        rows = db.list_maladies(args.query)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        if args.query:
            print(f"\nMaladies de '{args.query}':")
        else:
            print(f"\n{'ID':<4} {'Maladie':<30} {'Agent':<15} {'Traitement':<40}")
            print("-"*90)
        for r in rows:
            print(f"{r['id']:<4} {r['nom']:<30} {r.get('type_agent',''):<15} {r.get('type_traitement',''):<40}")

    elif args.action == "calendrier":
        fine = args.besoin_eau or args.categorie
        rows = db.get_calendrier(args.query, fine)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        if not rows:
            print("Aucun calendrier trouve")
            return
        print(f"\n{'Variete':<25} {'Semis':<15} {'Recolte':<15} {'Cycle':<8}")
        print("-"*65)
        for r in rows:
            semis = f"{r.get('mois_semis_debut','?')}-{r.get('mois_semis_fin','?')}"
            rec = f"{r.get('mois_recolte_debut','?')}-{r.get('mois_recolte_fin','?')}"
            print(f"{r.get('variete',''):<25} {semis:<15} {rec:<15} {r.get('duree_cycle_jours','?'):<8}")

    elif args.action == "irrigation":
        rows = db.get_irrigation(args.query, args.categorie)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
            return
        if not rows:
            print("Aucune donnee irrigation trouvee")
            return
        print(f"\n{'Variete':<25} {'Methode':<18} {'mm/sem':<8} {'Freq(j)':<8} {'Duree(min)':<10} {'Stade critique'}")
        print("-"*120)
        for r in rows:
            print(f"{r.get('variete',''):<25} {r.get('methode',''):<18} {str(r.get('frequence_mm_semaine','')):<8} {str(r.get('frequence_jours','')):<8} {str(r.get('duree_minutes','')):<10} {r.get('stade_critique','')}")


def cmd_predict(args):
    """Moteur de prediction IA."""
    from core.predictor import PredictorCLI
    PredictorCLI.handle(args)


def cmd_service(args):
    """Gestion centralisee de tous les services PixelOS."""
    from core.services import ServiceManager
    svc = ServiceManager()

    if args.action == "status":
        if args.json:
            print(json.dumps(svc.status(args.name), indent=2, ensure_ascii=False, default=str))
        else:
            print(svc.summary() if not args.name else "")
            if args.name:
                st = svc.status(args.name)
                for s in st:
                    icon = "RUN" if s["running"] else "STOP"
                    print(f"  {s['name']:<23} [{icon}] {s.get('status', '')}")

    elif args.action == "start":
        res = svc.start(args.name)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if args.name:
                print(f"  {res['status']}: {args.name}")
            else:
                for k, v in res.get("results", {}).items():
                    print(f"  {v['status']}: {k}")

    elif args.action == "stop":
        res = svc.stop(args.name)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("status") == "ok":
                print(f"  Arrete: {args.name or 'tous les services'}")

    elif args.action == "restart":
        print("  Redemarrage en cours...")
        res = svc.restart(args.name)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"  {res.get('status', 'ok')}: {args.name or 'tous les services'}")

    elif args.action == "logs":
        name = args.name or "pixelos-web"
        log_text = svc.logs(name, args.tail)
        print(log_text)

    elif args.action == "health":
        h = svc.health()
        if args.json:
            print(json.dumps(h, indent=2))
        else:
            print(f"\n  Sante PixelOS: {h['running']}/{h['total']} services en marche\n")
            for s in h["services"]:
                icon = "OK" if s["running"] else "KO"
                print(f"  [{icon}] {s['name']:<25} port {s['port']}")

    elif args.action == "autostart":
        st = svc.autostart_status()
        if args.name == "install":
            res = svc.autostart_install()
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"  Autostart: {res['status']} ({res.get('platform','?')})")
                if res.get("cmd"):
                    print(f"  Commande: {res['cmd']}")
        elif args.name == "remove":
            res = svc.autostart_remove()
            print(f"  Autostart: {res['status']}")
        else:
            if args.json:
                print(json.dumps(st, indent=2))
            else:
                if st.get("installed"):
                    print(f"  Autostart installe sur {st['platform']}")
                    if st.get("cmd"):
                        print(f"  Commande: {st['cmd']}")
                else:
                    print("  Autostart NON installe")
                    print("  -> pixelos service autostart install")


def cmd_energy(args):
    """Supervision energetique (solaire, batterie, charges)."""
    from core.energy import EnergyManager
    em = EnergyManager()

    if args.action == "status":
        s = em.summary()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Gestion Energetique PixelOS")
        print(f"  Panneaux: {s['panels']} ({s['peak_panel_kw']}kWc)"
              f" | Production: {s['current_solar_w']}W")
        print(f"  Charges: {s['active_loads']}/{s['loads']} actives"
              f" ({s['current_load_w']}W / {s['peak_load_kw']}kW max)")
        print(f"  Batterie: {s['battery_soc']}%"
              f" ({s['battery_capacity_kwh']}kWh)"
              f" | Reseau: {'OUI' if s['grid_available'] else 'NON'}")
        print(f"  Irradiation: {s['irradiance']} W/m2")

    elif args.action == "devices":
        panels = em.list_panels()
        loads = em.list_loads()
        if args.json:
            print(json.dumps({"panels": panels, "loads": loads},
                             indent=2, ensure_ascii=False))
            return
        print("\n  Panneaux solaires:")
        for p in panels:
            print(f"    {p['panel_id']:<20} {p['label']:<20}"
                  f" {p['peak_power_w']}Wc -> {p['current_power_w']}W"
                  f" [{'ON' if p['enabled'] else 'OFF'}]")
        print("\n  Charges:")
        for l in loads:
            print(f"    {l['load_id']:<22} {l['label']:<22}"
                  f" {l['current_draw_w']:>6}W ({l['nominal_w']}W max)"
                  f" [{l['state']}] p={l['priority']}")

    elif args.action == "solar":
        r = em.update_solar()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Production solaire:")
        print(f"  Irradiation: {r['irradiance']} W/m2")
        print(f"  Total: {r['total_w']}W")
        for pid, power in r["panels"].items():
            print(f"    {pid:<20} {power}W")

    elif args.action == "battery":
        b = em.battery.snapshot()
        if args.json:
            print(json.dumps(b, indent=2, ensure_ascii=False))
            return
        print(f"\n  Batterie {b['battery_id']}:")
        print(f"  SOC: {b['soc_pct']}% ({b['capacity_kwh']}kWh)")
        print(f"  Puissance: {b['current_power_w']}W"
              f" (charge max {b['max_charge_rate_w']}W"
              f" / decharge max {b['max_discharge_rate_w']}W)")
        print(f"  Cycles: {b['cycle_count']}")
        print(f"  Limites: min {b['min_soc_pct']}% max {b['max_soc_pct']}%")

    elif args.action == "load":
        if not args.load_id:
            print("  Erreur: specifiez --load-id")
            return
        state = args.state or "on"
        r = em.set_load_state(args.load_id, state, args.throttle)
        if r:
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            print(f"  {args.load_id}: {r['state']} ({r['current_draw_w']}W)")
        else:
            print(f"  Charge {args.load_id} introuvable")

    elif args.action == "cycle":
        r = em.run_cycle()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Cycle energetique:")
        print(f"  Solaire: {r['solar']['total_w']}W"
              f" (irradiance {r['solar']['irradiance']} W/m2)")
        print(f"  Batterie: SOC={r['battery']['soc']}%"
              f" ({r['battery_action']})")
        print(f"  Charge: {r['loads']['total_w']}W")
        print(f"  Net: {r['net_power_w']}W")
        if r["shed_decisions"]:
            print(f"  Load-shedding: {len(r['shed_decisions'])} decisions")

    elif args.action == "forecast":
        fc = em.forecast(args.hours)
        if args.json:
            print(json.dumps(fc, indent=2, ensure_ascii=False))
            return
        print(f"\n  Prevision solaire ({args.hours}h):")
        for f in fc:
            bar = "#" * max(1, int(f["estimated_kw"] * 4))
            print(f"  {f['hour']}  {f['estimated_kw']:>5.2f}kW {bar}")


def cmd_harvest(args):
    """Recolte : prevision, lots, etiquettes, inventaire."""
    from core.harvest import HarvestManager
    hm = HarvestManager()

    if args.action == "predict":
        if args.json:
            print(json.dumps({"zones": hm.predict_by_zone(),
                              "lines": hm.estimate_all()},
                             indent=2, ensure_ascii=False))
            return
        print("\n  Prevision de recolte:\n")
        for lid, r in enumerate(hm.estimate_all()):
            print(f"  {r['line_id']:<20} {r['expected_yield_kg']:>6.1f}kg  "
                  f"{r['estimated_value']:>8.2f}EUR  ({r['plant_count']} pieds)")
        zones = hm.predict_by_zone()
        print("\n  Par zone:")
        for zid, z in zones.items():
            print(f"  {z['zone_id']:<20} {z['expected_kg']:>6.1f}kg  "
                  f"{z['estimated_value']:>8.2f}EUR  ({z['lines']} lignes, {z['plants']} pieds)")

    elif args.action == "lines":
        lines = hm.list_lines()
        if args.json:
            print(json.dumps(lines, indent=2, ensure_ascii=False))
            return
        print(f"\n{'Ligne':<22} {'Zone':<14} {'Produit':<22} {'Pieds':<6} {'Estime kg':<10} {'Recolte kg':<12} {'Status'}")
        print("-"*90)
        for l in lines:
            print(f"{l['label']:<22} {l['zone_id']:<14} {l['product_id']:<22} {l['plant_count']:<6} "
                  f"{l['expected_yield_kg']:<10} {l['actual_yield_kg']:<12} {l['status']}")

    elif args.action == "batches":
        batches = hm.list_batches(args.status)
        if args.json:
            print(json.dumps(batches, indent=2, ensure_ascii=False))
            return
        if not batches:
            print("  Aucun lot")
            return
        print(f"\n{'Lot':<24} {'Produit':<20} {'Poids':<8} {'Total':<10} {'Qualite':<8} {'Status':<14} {'Dest':<12}")
        print("-"*95)
        for b in sorted(batches, key=lambda x: x["harvest_date"], reverse=True):
            print(f"{b['batch_id']:<24} {b['product_id']:<20} {b['weight_kg']:<8} "
                  f"{b['total_value']:<10.2f} {b['quality_grade']:<8} {b['status']:<14} {b.get('destination',''):<12}")

    elif args.action == "harvest":
        if not args.line_id or not args.weight:
            print("  Erreur: specifiez --line-id et --weight")
            return
        b = hm.create_batch(args.line_id, args.weight, args.price, args.quality or "A", args.date)
        if not b:
            print(f"  Ligne {args.line_id} introuvable ou inactive")
            return
        if args.json:
            print(json.dumps(b, indent=2, ensure_ascii=False))
            return
        print(f"  Lot cree: {b['batch_id']}")
        print(f"  Produit: {b['product_id']} | Poids: {b['weight_kg']}kg | Valeur: {b['total_value']:.2f}EUR")
        print(f"  Qualite: {b['quality_grade']} | Etiquette: {b['label_id']}")

    elif args.action == "labels":
        labels = []
        batches = hm.list_batches()
        for b in batches:
            lbls = hm.get_labels_for_batch(b["batch_id"])
            labels.extend(lbls)
        if args.json:
            print(json.dumps(labels, indent=2, ensure_ascii=False))
            return
        if not labels:
            print("  Aucune etiquette")
            return
        print(f"\n{'Etiquette':<24} {'Produit':<22} {'Zone':<14} {'Poids':<8} {'Total':<10} {'Qualite':<6}")
        print("-"*85)
        for l in labels:
            print(f"{l['label_id']:<24} {l['product']:<22} {l['zone']:<14} {l['weight_kg']:<8} {l['total']:<10.2f} {l['quality']:<6}")

    elif args.action == "inventory":
        inv = hm.inventory.snapshot()
        if args.json:
            print(json.dumps(inv, indent=2, ensure_ascii=False))
            return
        print(f"\n  Inventaire PixelOS")
        print(f"  En culture : {inv['en_culture_kg']} kg")
        print(f"  Pret vente : {inv['pret_vente_kg']} kg")
        print(f"  Distribue  : {inv['distribue_kg']} kg")
        print(f"  Vendu      : {inv['vendu_kg']} kg")
        print(f"  Stock total: {inv['total_stock_kg']} kg")
        print(f"  Valeur     : {inv['valeur_totale']:.2f} EUR")

    elif args.action == "suggestions":
        suggs = hm.get_harvest_suggestions()
        if args.json:
            print(json.dumps(suggs, indent=2, ensure_ascii=False))
            return
        if not suggs:
            print("  Aucune suggestion")
            return
        print(f"\n  Suggestions ({len(suggs)}):")
        for s in suggs:
            print(f"  [{s['priority']}] {s['message']}")


def cmd_onnx(args):
    """Export et inférence ONNX."""
    from ml.serving.onnx_engine import OnnxEngine
    engine = OnnxEngine(args.model)

    if args.action == "stats":
        s = engine.stats()
        print(f"\n  Backend: {s['backend']}")
        print(f"  Pickle : {s.get('pickle','?')} ({s.get('pickle_size_kb',0)} KB)")
        print(f"  ONNX   : {s.get('onnx','?')} ({s.get('onnx_size_kb',0)} KB)")
        print(f"  Quant  : {s.get('onnx_quant','?')} ({s.get('onnx_quant_size_kb',0)} KB)")

    elif args.action == "export":
        r = engine.export_onnx(quantize=not args.no_quant)
        if r.get("status") == "ok":
            print(f"  ONNX: {r['model']} ({r['size_kb']} KB)")
            if r.get("quantized", {}).get("status") == "ok":
                print(f"  Quant: {r['quantized']['model']} ({r['quantized']['size_kb']} KB, {r['quantized']['quant_type']})")
        else:
            print(f"  Erreur: {r.get('message','')}")

    elif args.action == "predict":
        data = {"humidite_sol": args.humidity or 45}
        if args.temp: data["temperature"] = args.temp
        if args.hum: data["humidite"] = args.hum
        if args.pression: data["pression"] = args.pression
        r = engine.predict(data)
        if r.get("status") == "error":
            print(f"  Erreur: {r['message']}")
            return
        print(f"\n  Backend: {r['backend']}")
        print(f"  Actuelle: {r['current_humidity']}% -> Predite: {r['predicted_humidity_6h']}%")
        print(f"  Eau: {r['water_needed_l_per_m2']} L/m2 | Confiance: {r['confidence_pct']}%")
        print(f"  >>> {r['recommendation']}")


def cmd_pipeline(args):
    """Pipeline d'auto-retrain ML."""
    from ml.pipeline import TrainingPipeline

    if args.action == "run":
        pl = TrainingPipeline(args.model, args.zone)
        trigger_task_id = args.task_id
        r = pl.run(days=args.days or 30, force=args.force,
                   trigger_task_id=trigger_task_id)
        if r["status"] == "completed":
            m = r.get("metrics", {})
            print(f"\n  Pipeline termine: {r['pipeline']}")
            print(f"  MAE: {m.get('mae','?')} | R2: {m.get('r2_score','?')} | Precision: {m.get('accuracy_pct','?')}%")
            print(f"  Echantillons: {m.get('samples',0)}")
            print(f"  Features importantes:")
            for f in m.get("features", []):
                bar = "#" * int(f["importance"] * 40)
                print(f"    {f['name']:<20} {bar} {f['importance']:.1%}")
        else:
            print(f"  Pipeline echoue au stage: {r.get('fail_stage','?')}")
            print(f"  Erreur: {r.get('stages',{}).get(r.get('fail_stage',''),{}).get('message','?')}")

    elif args.action == "versions":
        pl = TrainingPipeline(args.model)
        vers = pl.list_versions()
        if not vers:
            print("  Aucune version precedente")
            return
        print(f"\n  Versions de {args.model}:")
        for v in vers:
            print(f"  {v['file']:<50} {v['size_kb']} KB  {v['modified']}")

    elif args.action == "rollback":
        pl = TrainingPipeline(args.model)
        r = pl.rollback(args.version)
        if r.get("status") == "ok":
            print(f"  Restaure: {r['restored']}")
        else:
            print(f"  Erreur: {r.get('message','')}")


def cmd_web(args):
    """Lance l'interface web PixelOS."""
    from web.app import app
    port = args.port
    debug = args.debug
    print(f"PixelOS Web - http://0.0.0.0:{port}")
    print(f"Ctrl+C pour arreter")
    app.run(host="0.0.0.0", port=port, debug=debug)


def cmd_geothermal(args):
    """Controle geothermique (PID, sondes, vannes)."""
    from core.geothermal import GeothermalManager
    gm = GeothermalManager()

    if args.action == "status":
        s = gm.summary()
        zones = gm.list_zones()
        if args.json:
            print(json.dumps({"summary": s, "zones": zones}, indent=2,
                             ensure_ascii=False))
            return
        mode_icons = {"heating": " CH", "cooling": " FR", "idle": " --"}
        print(f"\n  Controle Geothermique PixelOS")
        print(f"  Zones: {s['total_zones']} | Chauffage: {s['heating_active']} "
              f"| Refroid: {s['cooling_active']} | Moy: {s['avg_temp']}C\n")
        for z in zones:
            icon = mode_icons.get(z["mode"], " --")
            flag = "ON" if z["enabled"] else "OFF"
            print(f"  {icon} {z['label']:<20} T={z['current_temp']:.1f}C "
                  f"(cible {z['target_temp']}C) vanne={z['valve_position']:.0f}% "
                  f"[{z['mode']}] {flag}")

    elif args.action == "zones":
        zs = gm.list_zones()
        if args.json:
            print(json.dumps(zs, indent=2, ensure_ascii=False))
            return
        for z in zs:
            print(f"  {z['zone_id']:<15} {z['label']:<20} "
                  f"T={z['current_temp']:.1f}C/{z['target_temp']}C "
                  f"mode={z['mode']} enable={z['enabled']}")

    elif args.action == "set":
        z = gm.update_zone(args.zone, target_temp=args.target,
                           hysteresis=args.hysteresis)
        if z:
            print(f"  Zone {args.zone} mise a jour: T={z['target_temp']}C, "
                  f"hysteresis={z['hysteresis']}C")
        else:
            print(f"  Zone {args.zone} introuvable")

    elif args.action == "cycle":
        r = gm.run_cycle()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for zid, res in r.items():
            print(f"  {zid:<15} T={res['current_temp']:.1f}C "
                  f"vanne={res['valve_position']:.0f}% mode={res['mode']}")

    elif args.action == "anomalies":
        anomalies = gm.check_anomalies()
        if args.json:
            print(json.dumps(anomalies, indent=2, ensure_ascii=False))
            return
        if not anomalies:
            print("  Aucune anomalie")
            return
        for a in anomalies:
            print(f"  [{a['severity']}] {a['zone']}: {a['message']}")


def cmd_space(args):
    """Gestion des espaces (serres, pepinieres, champs)."""
    from core.spaces import SpaceManager
    sm = SpaceManager()

    if args.action == "list":
        s = sm.summary()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Espaces PixelOS ({s['total']})")
        print(f"  Capteurs: {s['sensors']} | Controles: {s['controls']} | Zones: {s['sub_zones']}\n")
        for e in s["espaces"]:
            auto_parts = []
            if e.get("auto_irrigation"): auto_parts.append("IRRIG")
            if e.get("auto_climate"): auto_parts.append("CLIM")
            if e.get("auto_light"): auto_parts.append("LIGHT")
            auto_str = f" [{' '.join(auto_parts)}]" if auto_parts else ""
            print(f"  {e['type']:<15} {e['label']:<20} {e['location']}{auto_str}")

    elif args.action == "show":
        e = sm.get_espace(args.espace_id)
        if not e:
            print(f"  Espace {args.espace_id} introuvable")
            return
        if args.json:
            print(json.dumps(e, indent=2, ensure_ascii=False))
            return
        print(f"\n  {e['label']} ({e['type']}) @ {e['location']}")
        print(f"  Auto: irrigation={'ON' if e.get('auto_irrigation') else 'OFF'} "
              f"climat={'ON' if e.get('auto_climate') else 'OFF'} "
              f"lumiere={'ON' if e.get('auto_light') else 'OFF'}")
        print(f"  Capteurs:")
        for sid, s in e["sensors"].items():
            alarm = " !" if s["status"] in ("alarm_low", "alarm_high") else ""
            print(f"    {s['label']:<25} {s['value']}{s['unit']} [{s['status']}]{alarm}")
        print(f"  Controles:")
        for cid, c in e["controls"].items():
            auto = " [AUTO]" if c.get("auto_mode") else ""
            print(f"    {c['label']:<25} {c['state']} ({c['value']}%){auto}")
        print(f"  Sous-zones:")
        for zid, z in e["sub_zones"].items():
            culture = z.get("culture", "") or z.get("product_id", "libre")
            print(f"    {z['label']:<25} {z['area_m2']}m2 [{culture}]")

    elif args.action == "sensors":
        r = sm.read_sensors(args.espace_id)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for eid, sensors in r.items():
            print(f"\n  {eid}:")
            for sid, val in sensors.items():
                print(f"    {sid}: {val}")

    elif args.action == "control":
        if not args.espace_id or not args.target:
            print("  Erreur: specifiez espace_id et control_id")
            return
        r = sm.control_action(args.espace_id, args.target,
                              args.state, args.value)
        if r:
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            print(f"  {args.target}: {r['state']} ({r['value']}%)")
        else:
            print(f"  Control {args.target} introuvable")

    elif args.action == "assign":
        if not args.espace_id or not args.target or not args.product_id:
            print("  Erreur: specifiez espace_id, sub_zone_id et --product-id")
            return
        r = sm.assign_product(args.espace_id, args.target,
                              args.product_id, args.planted_at)
        if r:
            print(f"  {args.target} <- {args.product_id} (plante le {r['planted_at']})")
        else:
            print(f"  Assignation echouee")

    elif args.action == "add":
        r = sm.add_espace(args.espace_id, args.type or "serre",
                          args.label or "", args.location or "",
                          args.description or "", confirm=args.confirm)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        if r.get("status") == "pending_confirmation":
            print(f"  Confirmation requise pour ajouter {args.espace_id}")
            print(f"  Ajoutez --confirm pour confirmer")
            print(f"  Apercu: {r['preview']}")
        elif r.get("status") == "ok":
            print(f"  Espace ajoute: {args.espace_id}")
        else:
            print(f"  Erreur: {r.get('error', 'inconnue')}")

    elif args.action == "auto":
        if not args.espace_id:
            print("  Erreur: specifiez espace_id")
            return
        atype = args.auto_type or "irrigation"
        enabled = args.enabled
        r = sm.set_auto_mode(args.espace_id, atype, enabled)
        if r:
            print(f"  {args.espace_id}: auto_{atype} = {'ON' if enabled else 'OFF'}")
        else:
            print(f"  Espace {args.espace_id} introuvable")

    elif args.action == "auto-cycle":
        r = sm.auto_control_cycle(args.espace_id)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Cycle auto-controle: {r['count']} actions")
        for a in r["actions"]:
            print(f"  -> {a}")


def cmd_lifecycle(args):
    """Cycles de vie des produits agricoles."""
    from core.lifecycle import LifecycleManager
    lm = LifecycleManager()

    if args.action == "products":
        ps = lm.list_products()
        if args.json:
            print(json.dumps(ps, indent=2, ensure_ascii=False))
            return
        print(f"\n  Produits PixelOS ({len(ps)})")
        for p in ps:
            stages = ", ".join(s["name"] for s in p.get("stages", []))
            print(f"  {p['product_id']:<25} {p['label']:<25} "
                  f"{p['cycle_days']}j [{stages}]")

    elif args.action == "plantations":
        pls = lm.list_plantations()
        if args.json:
            print(json.dumps(pls, indent=2, ensure_ascii=False))
            return
        print(f"\n  Plantations ({len(pls)})")
        for pl in pls:
            print(f"  {pl['plantation_id']:<12} {pl['label'] or pl['product_id']:<25} "
                  f"@{pl['espace_id']}/{pl['sub_zone_id']:<10} "
                  f"J{pl['day_of_cycle']} [{pl['status']}]")

    elif args.action == "plant":
        if not args.product_id or not args.espace:
            print("  Erreur: specifiez product_id et --espace")
            return
        pl = lm.create_plantation(args.product_id, args.espace,
                                  args.sub_zone or "", args.quantity,
                                  args.label or "", args.planted_at)
        if args.json:
            print(json.dumps(pl, indent=2, ensure_ascii=False))
            return
        print(f"  Plantation creee: {pl['plantation_id']} "
              f"({pl['label'] or pl['product_id']} @ {pl['espace_id']})")

    elif args.action == "tasks":
        tasks = lm.generate_tasks(args.plantation_id, args.force)
        if args.json:
            print(json.dumps(tasks, indent=2, ensure_ascii=False))
            return
        print(f"  {len(tasks)} taches generees")

    elif args.action == "suggestions":
        suggs = lm.get_suggestions(args.espace)
        if args.json:
            print(json.dumps(suggs, indent=2, ensure_ascii=False))
            return
        if not suggs:
            print("  Aucune suggestion")
            return
        print(f"\n  Suggestions ({len(suggs)})")
        for s in suggs:
            print(f"  [{s['priority']}] {s['message']}")

    elif args.action == "harvest":
        if not args.plantation_id:
            print("  Erreur: specifiez plantation_id")
            return
        pl = lm.update_plantation(args.plantation_id,
                                  status="harvested",
                                  harvested_at=datetime.now().strftime("%Y-%m-%d"))
        if pl:
            print(f"  {args.plantation_id} marquee recoltee")
        else:
            print(f"  Plantation {args.plantation_id} introuvable")


def cmd_tasks(args):
    from core.tasks import TaskManager
    tm = TaskManager()

    if args.action == "list":
        tasks = tm.search(args.query, args.status, args.categorie,
                          args.priorite, args.zone)
        if args.json:
            print(json.dumps(tasks, indent=2, ensure_ascii=False))
            return
        if not tasks:
            print("  Aucune tache")
            return
        print(f"\n{'ID':<10} {'Titre':<30} {'Status':<14} {'Prio':<8} {'Echeance':<12} {'Categorie'}")
        print("-" * 90)
        for t in tasks:
            s = {"todo":"A faire","in_progress":"En cours","done":"Terminee","cancelled":"Annulee"}.get(t["status"], t["status"])
            d = (t.get("echeance") or "")[:10]
            print(f"{t['id']:<10} {t['title']:<30} {s:<14} {t.get('priorite',''):<8} {d:<12} {t.get('categorie','')}")

    elif args.action == "show":
        t = tm.get(args.task_id)
        if not t:
            print(f"Tache {args.task_id} introuvable")
            return
        if args.json:
            print(json.dumps(t, indent=2, ensure_ascii=False))
            return
        print(f"\n=== {t['title']} ===")
        print(f"  ID        : {t['id']}")
        print(f"  Status    : {t['status']}")
        print(f"  Priorite  : {t.get('priorite','medium')}")
        print(f"  Categorie : {t.get('categorie','autre')}")
        print(f"  Echeance  : {t.get('echeance','-')}")
        print(f"  Assigne   : {t.get('assigne','-')}")
        print(f"  Zone      : {t.get('zone','-')}")
        print(f"  Plante    : {t.get('plante','-')}")
        print(f"\n  {t.get('description','')}")

    elif args.action == "create":
        t = tm.create(args.title, args.description or "",
                      args.categorie or "autre", args.priorite or "medium",
                      args.echeance, args.assigne or "",
                      args.zone or "", args.plante or "")
        print(f"  Tache creee: {t['id']} - {t['title']}")

    elif args.action == "edit":
        kwargs = {}
        for k in ("title","description","categorie","priorite",
                  "status","echeance","assigne","zone","plante"):
            v = getattr(args, k, None)
            if v is not None:
                kwargs[k] = v
        t = tm.update(args.task_id, **kwargs)
        if t:
            print(f"  Tache mise a jour: {t['id']}")
        else:
            print(f"  Tache {args.task_id} introuvable")

    elif args.action == "delete":
        if tm.delete(args.task_id):
            print(f"  Tache supprimee: {args.task_id}")
        else:
            print(f"  Tache {args.task_id} introuvable")

    elif args.action == "stats":
        s = tm.stats()
        if args.json:
            print(json.dumps(s, indent=2))
            return
        print(f"\n  Total     : {s['total']}")
        print(f"  A faire   : {s['todo']}")
        print(f"  En cours  : {s['in_progress']}")
        print(f"  Terminees : {s['done']}")
        print(f"  Annulees  : {s['cancelled']}")
        print(f"  Urgentes  : {s['urgent']}")
        print(f"  En retard : {s['en_retard']}")
        print(f"\n  Par categorie:")
        for cat, count in s["categories"].items():
            if count > 0:
                print(f"    {cat}: {count}")

    elif args.action == "alerts":
        alerts = tm.alerts()
        if args.json:
            print(json.dumps(alerts, indent=2))
            return
        if not alerts:
            print("  Aucune alerte tache")
            return
        print(f"\n{'ID':<10} {'Titre':<30} {'Type':<10} {'Zone':<15} {'Echeance':<12}")
        print("-" * 80)
        for a in alerts:
            d = (a.get("echeance") or "")[:10]
            print(f"{a['id']:<10} {a['title']:<30} {a['type']:<10} {a.get('zone',''):<15} {d:<12}")


def cmd_program(args):
    """Programmes PixelOS : Text, Audio, Video."""
    from core.programs import ProgramManager
    pm = ProgramManager()

    if args.program == "text":
        if args.action == "list":
            notes = pm.notes_list()
            if args.categorie:
                notes = [n for n in notes if n.get("categorie") == args.categorie]
            if args.json:
                print(json.dumps(notes, indent=2, ensure_ascii=False))
                return
            if not notes:
                print("  Aucune note")
                return
            print(f"\n{'ID':<10} {'Titre':<30} {'Categorie':<15} {'Modifie'}")
            print("-" * 70)
            for n in notes:
                d = n["updated"][:10] if n.get("updated") else ""
                print(f"{n['id']:<10} {n['title']:<30} {n.get('categorie',''):<15} {d}")

        elif args.action == "show":
            note = pm.note_get(args.note_id)
            if not note:
                print(f"Note {args.note_id} introuvable")
                return
            if args.json:
                print(json.dumps(note, indent=2, ensure_ascii=False))
                return
            print(f"\n=== {note['title']} ===")
            print(f"  Categorie : {note.get('categorie', 'general')}")
            print(f"  Cree      : {note.get('created', '')[:16]}")
            print(f"  Modifie   : {note.get('updated', '')[:16]}")
            print(f"\n{note['content']}")

        elif args.action == "create":
            note = pm.note_create(args.title, args.content or "", args.categorie or "general")
            print(f"  Note creee: {note['id']} - {note['title']}")

        elif args.action == "edit":
            note = pm.note_update(args.note_id, args.title, args.content, args.categorie)
            if note:
                print(f"  Note mise a jour: {note['id']}")
            else:
                print(f"  Note {args.note_id} introuvable")

        elif args.action == "delete":
            if pm.note_delete(args.note_id):
                print(f"  Note supprimee: {args.note_id}")
            else:
                print(f"  Note {args.note_id} introuvable")

    elif args.program == "audio":
        if args.action == "list":
            items = pm.audio_list()
            if args.json:
                print(json.dumps(items, indent=2, ensure_ascii=False))
                return
            if not items:
                print("  Aucun enregistrement audio")
                return
            print(f"\n{'ID':<10} {'Titre':<35} {'Taille':<10} {'Date'}")
            print("-" * 70)
            for a in items:
                size = f"{a['size']/1024:.1f}KB" if a.get('size') else "?"
                d = a["created"][:10] if a.get("created") else ""
                print(f"{a['id']:<10} {a.get('title',''):<35} {size:<10} {d}")

        elif args.action == "delete":
            if pm.audio_delete(args.audio_id):
                print(f"  Audio supprime: {args.audio_id}")
            else:
                print(f"  Audio {args.audio_id} introuvable")

    elif args.program == "video":
        if args.action == "list":
            items = pm.video_list()
            if args.json:
                print(json.dumps(items, indent=2, ensure_ascii=False))
                return
            if not items:
                print("  Aucune video")
                return
            print(f"\n{'ID':<10} {'Titre':<35} {'Type':<10} {'Date'}")
            print("-" * 70)
            for v in items:
                d = v["created"][:10] if v.get("created") else ""
                print(f"{v['id']:<10} {v.get('title',''):<35} {v.get('source_type','url'):<10} {d}")

        elif args.action == "add":
            v = pm.video_add(args.source, args.title, args.type or "url", args.duration or 0)
            print(f"  Video ajoutee: {v['id']} - {v['title']}")

        elif args.action == "delete":
            if pm.video_delete(args.video_id):
                print(f"  Video supprimee: {args.video_id}")
            else:
                print(f"  Video {args.video_id} introuvable")


def cmd_lab(args):
    """Pôle laboratoire : sol, microbiome, microscopie, croissance, génétique."""
    from core.laboratory import LabManager
    lm = LabManager()

    if args.action == "samples":
        samples = lm.list_samples(args.sample_type, args.status, args.location)
        if args.json:
            print(json.dumps(samples, indent=2, ensure_ascii=False))
            return
        if not samples:
            print("  Aucun échantillon")
            return
        print(f"\n{'Sample':<20} {'Type':<10} {'Location':<20} {'Status':<12} {'Date'}")
        print("-"*75)
        for s in samples:
            d = (s.get("collection_date") or "")[:10]
            print(f"{s['sample_id']:<20} {s['sample_type']:<10} {s.get('location',''):<20} {s['status']:<12} {d}")

    elif args.action == "sample-create":
        s = lm.create_sample(args.sample_type or "sol", args.source or "",
                             args.location or "", args.collector or "",
                             args.depth, args.mass, args.notes or "")
        print(f"  Échantillon créé: {s['sample_id']} ({s['sample_type']} @ {s['location']})")

    elif args.action == "sample-get":
        s = lm.get_sample(args.sample_id)
        if not s:
            print(f"  Échantillon {args.sample_id} introuvable")
            return
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  {s['sample_id']} — {s['sample_type']} @ {s['location']}")
        print(f"  Statut: {s['status']} | Collecteur: {s.get('collector','')} | Date: {s.get('collection_date','')[:10]}")
        if s.get("depth_cm"): print(f"  Profondeur: {s['depth_cm']} cm")
        if s.get("mass_g"): print(f"  Masse: {s['mass_g']} g")
        if s.get("notes"): print(f"  Notes: {s['notes']}")

    elif args.action == "soil":
        if args.sub == "create":
            data = {"ph": args.ph, "matiere_organique_pct": args.mo,
                    "n_total_pct": args.n, "p_phosphore_mg_kg": args.p,
                    "k_potassium_mg_kg": args.k, "cec_meq_100g": args.cec,
                    "soil_type": args.soil_type, "texture": args.texture,
                    "conductivite_us_cm": args.conductivite,
                    "analyse_date": args.date}
            if args.fe: data["fe_fer_mg_kg"] = args.fe
            if args.mn: data["mn_manganese_mg_kg"] = args.mn
            if args.zn: data["zn_zinc_mg_kg"] = args.zn
            r = lm.create_soil_analysis(args.sample_id, data)
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            fi = r.get("fertility_index", {})
            print(f"  Analyse sol enregitrée: {args.sample_id}")
            print(f"  Fertilité: {fi.get('index',0)}% ({fi.get('interpretation','')})")
            for rec in r.get("recommendations", []):
                print(f"  [{rec['priority']}] {rec['message']}")
        elif args.sub == "get":
            r = lm.get_soil_analysis(args.sample_id)
            if not r:
                print(f"  Analyse {args.sample_id} introuvable")
                return
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            print(f"\n  Analyse sol: {args.sample_id}")
            print(f"  pH: {r.get('ph')} | MO: {r.get('matiere_organique_pct')}%")
            print(f"  N: {r.get('n_total_pct')}% | P: {r.get('p_phosphore_mg_kg')} mg/kg | K: {r.get('k_potassium_mg_kg')} mg/kg")
            fi = r.get("fertility_index", {})
            print(f"  Fertilité: {fi.get('index',0)}% — {fi.get('interpretation','')}")

    elif args.action == "microbiome":
        if args.sub == "create":
            data = {"method": args.method or "metagenomique_16S",
                    "total_bacteria_cfu_g": args.bacteria,
                    "total_fungi_cfu_g": args.fungi,
                    "bacterial_diversity_shannon": args.shannon,
                    "fungal_diversity_shannon": args.f_shannon}
            r = lm.create_microbiome(args.sample_id, data)
            di = r.get("diversity_index", {})
            print(f"  Microbiome enregistré: {args.sample_id}")
            print(f"  Diversité: {di.get('index',0)}% — {di.get('interpretation','')}")
        elif args.sub == "get":
            r = lm.get_microbiome(args.sample_id)
            if not r:
                print(f"  Microbiome {args.sample_id} introuvable")
                return
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            di = r.get("diversity_index", {})
            print(f"  Microbiome: {args.sample_id}")
            print(f"  Bactéries: {r.get('total_bacteria_cfu_g')} CFU/g | Shannon: {r.get('bacterial_diversity_shannon')}")
            print(f"  Champignons: {r.get('total_fungi_cfu_g')} CFU/g | Shannon: {r.get('fungal_diversity_shannon')}")
            print(f"  Santé: {di.get('index',0)}% — {di.get('interpretation','')}")

    elif args.action == "microscopy":
        if args.sub == "create":
            data = {"magnification": args.mag or 400,
                    "stain": args.stain or "", "notes": args.notes or ""}
            r = lm.create_microscopy(args.sample_id, data)
            print(f"  Observation microscopique créée: {r['observation_id']}")
        elif args.sub == "get":
            r = lm.get_microscopy(args.obs_id)
            if not r:
                print(f"  Observation {args.obs_id} introuvable")
                return
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            print(f"  Observation: {r['observation_id']}")
            print(f"  Microscope: {r.get('microscope','')} | Grossissement: {r.get('magnification')}x")

    elif args.action == "growth":
        if args.sub == "track":
            r = lm.create_growth_track(args.plant_id, args.product_id or "")
            print(f"  Suivi croissance créé: {args.plant_id}")
        elif args.sub == "record":
            r = lm.record_growth(args.plant_id, args.stage or "croissance_végétative",
                                  args.height, args.leaf_count, args.leaf_area,
                                  args.stem_diameter, args.root_length,
                                  args.branching, args.spad, args.ndvi)
            if r:
                print(f"  Observation enregistrée J{r.get('day_of_growth','?')}: {args.plant_id}")
            else:
                print(f"  Plant {args.plant_id} introuvable")
        elif args.sub == "summary":
            r = lm.growth_summary(args.plant_id)
            if not r:
                print(f"  Plant {args.plant_id} introuvable")
                return
            print(f"  {r.get('plant_id')} — {r.get('days_tracked',0)} jours")
            print(f"  Stade: {r.get('current_stage','')} | Hauteur: {r.get('current_height_cm','?')} cm")
            gr = r.get("growth_rate", {})
            print(f"  Croissance: {gr.get('rate_cm_per_day',0)} cm/j")

    elif args.action == "genetics":
        if args.sub == "create":
            r = lm.create_genetic_profile(args.plant_id, args.species or "", args.variety or "")
            print(f"  Profil génétique créé: {args.plant_id}")
        elif args.sub == "get":
            r = lm.get_genetic_profile(args.plant_id)
            if not r:
                print(f"  Profil {args.plant_id} introuvable")
                return
            if args.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                return
            print(f"  Profil génétique: {args.plant_id}")
            print(f"  Espèce: {r.get('species','')} | Variété: {r.get('variety','')}")
            print(f"  SNPs: {len(r.get('snp_markers',[]))} | Gènes: {len(r.get('genes_of_interest',[]))}")

    elif args.action == "heatmap":
        h = lm.heatmap_data()
        if args.json:
            print(json.dumps(h, indent=2, ensure_ascii=False))
            return
        print("\n  Carte de chaleur — Santé des sols:")
        for zone, data in h.get("soil_health", {}).items():
            bar = "#" * max(1, int(data.get("avg_fertility", 0) / 5))
            print(f"  {zone:<20} Fertilité: {data.get('avg_fertility',0):>5.1f}% {bar} (n={data.get('count',0)})")
        print("\n  Microbiome:")
        for zone, data in h.get("microbiome_diversity", {}).items():
            bar = "#" * max(1, int(data.get("avg_diversity", 0) / 5))
            print(f"  {zone:<20} Diversité: {data.get('avg_diversity',0):>5.1f}% {bar} (n={data.get('count',0)})")

    elif args.action == "stats":
        s = lm.stats()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Pôle Laboratoire PixelOS")
        print(f"  Échantillons: {s['total_samples']}")
        for t, c in s.get("samples_by_type", {}).items():
            print(f"    {t}: {c}")
        print(f"  Analyses sol: {s['soil_analyses']}")
        print(f"  Microbiomes: {s['microbiomes']}")
        print(f"  Observations microscopiques: {s['microscopies']}")
        print(f"  Suivis croissance: {s['growth_tracks']}")
        print(f"  Profils génétiques: {s['genetic_profiles']}")
        print(f"  Fertilité moyenne: {s.get('avg_fertility_index',0)}%")


def cmd_omics(args):
    """Bioinformatique : séquences, alignement, phylogénie, métagénomique."""
    from core.omics import OmicsPipeline
    op = OmicsPipeline()

    if args.action == "genomes":
        genomes = op.importer.list_genomes(args.species)
        if args.json:
            print(json.dumps(genomes, indent=2, ensure_ascii=False))
            return
        if not genomes:
            print("  Aucun génome")
            return
        print(f"\n{'Fichier':<50} {'Taille KB':<12} {'Modifié'}")
        print("-"*80)
        for g in genomes:
            print(f"{g['file']:<50} {g['size_kb']:<12} {g['modified'][:19]}")

    elif args.action == "import":
        r = op.importer.import_fasta(args.fasta, args.species or "", args.variety or "")
        if r.get("status") == "ok":
            qc = r.get("quality", {})
            print(f"  Importé: {r['file']}")
            print(f"  Séquences: {r.get('records',0)} | GC: {qc.get('avg_gc_pct','?')}% | Total: {qc.get('total_bases',0)} pb")
        else:
            print(f"  Erreur: {r.get('message','')}")

    elif args.action == "align":
        if not args.fasta1:
            print("  Erreur: spécifiez --fasta1 et --fasta2")
            return
        with open(args.fasta1) as f:
            from Bio import SeqIO
            s1 = str(next(SeqIO.parse(f, "fasta")).seq)
        with open(args.fasta2) as f:
            s2 = str(next(SeqIO.parse(f, "fasta")).seq)
        from core.omics import SequenceAligner
        r = SequenceAligner.pairwise(s1, s2)
        if args.json:
            print(json.dumps(r, indent=2))
            return
        print(f"  Alignement: score={r.get('score',0)} identité={r.get('identity_pct',0)}%")
        print(f"  Longueur: {r.get('alignment_length',0)} pb | Gaps: {r.get('gaps',0)}")

    elif args.action == "phylogeny":
        if not args.alignment:
            print("  Erreur: spécifiez --alignment")
            return
        from core.omics import PhylogenyBuilder
        r = PhylogenyBuilder.from_alignment(args.alignment, args.method or "nj")
        print(f"  Arbre phylogénétique ({r.get('method','')}): {r.get('output','')}")
        print(f"  Taxons: {r.get('tips',0)} | Longueur: {r.get('total_branch_length',0)}")

    elif args.action == "metagenomics":
        from core.omics import Metagenomics
        mg = Metagenomics()
        if args.sub == "classify" and args.fasta:
            r = mg.classify_16s(args.fasta)
            print(f"  Classification 16S: {r.get('sequences_classified',0)} séquences")
            print(f"  Taxon dominant: {r.get('dominant_taxa',{})}")
        elif args.sub == "diversity":
            import numpy as np
            data = np.random.randint(0, 100, 50)
            r = mg.alpha_diversity(data)
            print(f"  Diversité alpha: Shannon={r.get('shannon',0)} Simpson={r.get('simpson',0)} Chao1={r.get('chao1',0)}")
        else:
            print("  Utilisation: pixelos omics metagenomics --sub classify|diversity --fasta <file>")

    elif args.action == "stats":
        s = op.stats()
        if args.json:
            print(json.dumps(s, indent=2))
            return
        print(f"\n  Bioinformatique PixelOS")
        print(f"  Fichiers génomes: {s.get('genome_files',0)} ({s.get('genome_size_mb',0)} MB)")
        print(f"  Alignements: {s.get('alignment_files',0)}")
        print(f"  Arbres phylogénétiques: {s.get('tree_files',0)}")


def cmd_ontology(args):
    """Ontologie agricole : profils plantes, échanges inter-systèmes."""
    from core.ontology import ontology

    if args.action == "traits":
        traits = ontology.list_all_species()
        if args.json:
            print(json.dumps(traits, indent=2, ensure_ascii=False))
            return
        print(f"\n  Profils plantes ({len(traits)}):")
        for t in traits:
            print(f"  {t['species_id']:<20} {t.get('scientific_name',''):<35} {t.get('family','')}")

    elif args.action == "trait-create":
        from core.ontology import PlantTrait
        pt = PlantTrait(args.species_id)
        pt.scientific_name = args.scientific_name or ""
        pt.common_name = args.common_name or ""
        pt.family = args.family or ""
        pt.genus = args.genus or ""
        pt.origin_region = args.origin or ""
        if args.koppen: pt.koppen_zones = args.koppen.split(",")
        r = ontology.save_plant_trait(pt)
        print(f"  Profil créé: {args.species_id} ({pt.scientific_name})")

    elif args.action == "trait-get":
        r = ontology.get_plant_trait(args.species_id)
        if not r:
            print(f"  Profil {args.species_id} introuvable")
            return
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  {r.get('scientific_name','')} ({r.get('common_name','')})")
        print(f"  Famille: {r.get('family','')} | Genre: {r.get('genus','')}")
        print(f"  Origine: {r.get('origin_region','')} | Zones Köppen: {', '.join(r.get('koppen_zones',[]))}")
        traits = r.get("traits", {})
        if traits:
            print(f"  Traits:")
            for k, v in traits.items():
                print(f"    {k}: {v}")

    elif args.action == "compare":
        r = ontology.compare_species(args.species_a, args.species_b)
        if not r:
            print("  Espèces introuvables")
            return
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Comparaison: {r.get('species_a','')} vs {r.get('species_b','')}")
        print(f"  Similarité: {r.get('similarity_pct',0)}%")
        for k, v in r.get("differences", {}).items():
            print(f"  Diff: {k} — {v.get('a')} / {v.get('b')}")

    elif args.action == "export":
        r = ontology.export_plant_profile(args.species_id)
        if not r:
            print(f"  Profil {args.species_id} introuvable")
            return
        print(json.dumps(r, indent=2, ensure_ascii=False))

    elif args.action == "exchanges":
        exc = ontology.list_exchanges(args.direction)
        if args.json:
            print(json.dumps(exc, indent=2, ensure_ascii=False))
            return
        print(f"\n  Échanges ({len(exc)}):")
        for e in exc:
            print(f"  {e.get('record_id','')} {e.get('remote_system','')} ({e.get('exchange_direction','')}) — {e.get('status','')}")

    elif args.action == "stats":
        s = ontology.stats()
        if args.json:
            print(json.dumps(s, indent=2))
            return
        print(f"\n  Ontologie Agricole PixelOS")
        print(f"  Profils espèces: {s.get('species_profiles',0)}")
        print(f"  Échanges: {s.get('exchanges',0)} (envoyés: {s.get('sent',0)} reçus: {s.get('received',0)})")
        print(f"  Zones Köppen: {s.get('koppen_zones_available',0)}")
        print(f"  Stades phénologiques BBCH: 20")


def cmd_vision(args):
    """Vision par ordinateur : segmentation, croissance, NDVI, racines, maladies."""
    from core.vision import VisionPipeline
    vp = VisionPipeline()

    if args.action == "segment":
        r = vp.segmenter.segment(args.image)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Segmentation: {args.image}")
        print(f"  Couverture végétale: {r.get('plant_coverage_pct',0)}%")
        for region, data in r.get("regions", {}).items():
            print(f"    {region:<20} {data.get('area_pct',0):>6.2f}% ({data.get('pixels',0)} px)")

    elif args.action == "growth":
        images = args.images.split(",") if args.images else [args.image]
        r = vp.analyze_growth_series(images)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        gr = r.get("growth", {})
        print(f"  Croissance: {len(images)} images")
        print(f"  Surface initiale: {gr.get('initial_area_cm2',0)} cm²")
        print(f"  Surface finale: {gr.get('final_area_cm2',0)} cm²")
        print(f"  Taux: {gr.get('growth_rate_cm2_per_day',0)} cm²/j")
        print(f"  Croissance relative: {gr.get('relative_growth_pct',0)}%")

    elif args.action == "ndvi":
        r = vp.calculate_ndvi(args.nir, args.red)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  NDVI moyen: {r.get('mean_ndvi',0)}")
        cl = r.get("classification", {})
        print(f"  Sain: {cl.get('healthy_pct',0)}% | Modéré: {cl.get('moderate_pct',0)}% | Stressé: {cl.get('stressed_pct',0)}%")
        print(f"  Interprétation: {r.get('interpretation','')}")

    elif args.action == "root":
        r = vp.analyze_root(args.image)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Analyse racinaire: {args.image}")
        print(f"  Longueur estimée: {r.get('estimated_length_cm',0)} cm")
        print(f"  Points de branchement: {r.get('branch_points',0)}")
        print(f"  Densité: {r.get('branching_density',0)}")

    elif args.action == "disease":
        r = vp.disease.detect_symptoms(args.image)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Détection maladies: {args.image}")
        print(f"  Sévérité: {r.get('severity','')}")
        for symptom, data in r.get("symptoms", {}).items():
            if data.get("area_pct", 0) > 0.5:
                print(f"    {symptom:<20} {data.get('area_pct',0):>6.2f}%")

    elif args.action == "height":
        r = vp.growth.height_from_image(args.image)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        bb = r.get("bounding_box", {})
        print(f"  Hauteur estimée: {r.get('height_pixels',0)} px (ratio: {r.get('height_ratio',0)})")
        print(f"  Bounding box: x={bb.get('x')} y={bb.get('y')} w={bb.get('width')} h={bb.get('height')}")

    elif args.action == "leaf-area":
        r = vp.segmenter.estimate_leaf_area(args.image)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Surface foliaire estimée: {r.get('estimated_area_cm2',0)} cm²")

    elif args.action == "stats":
        s = vp.stats()
        if args.json:
            print(json.dumps(s, indent=2))
            return
        print(f"\n  Vision par Ordinateur PixelOS")
        print(f"  Images brutes: {s.get('raw_images',0)}")
        print(f"  Images traitées: {s.get('processed_images',0)}")
        print(f"  {s.get('has_opencv',False)}")


def cmd_production(args):
    """Gestion de production: préparation sol, plantation, plans."""
    from core.production import production_manager as pm

    if args.action == "dashboard":
        data = pm.full_dashboard()
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
            return
        s = data["stats"]
        print(f"\n  Production — {s['active_plans']} plans actifs")
        print(f"  | Préparations sol: {s['total_soil_preps']} "
              f"Plantations: {s['total_plantings']} "
              f"Plans: {s['total_plans']}")
        print(f"  | Rendement estimé: {s['estimated_total_yield_kg']} kg")
        print(f"  | Plants: {s['total_plants']}")

    elif args.action == "soil-list":
        items = pm.list_soil_preps(
            space_id=args.space, status=args.status)
        if args.json:
            print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
            return
        if not items:
            print("  Aucune préparation sol")
            return
        print(f"\n  Préparations sol ({len(items)})")
        for s in items:
            print(f"  {s['id']:20} {s['name']:25} {s.get('status','?'):12} "
                  f"{s.get('preparation_type','?'):14} {s.get('area_m2',0):>6}m2 "
                  f"début: {s.get('start_date','')[:10]}")

    elif args.action == "soil-create":
        sp = pm.create_soil_prep(
            name=args.name or args.sub_zone or "sol",
            space_id=args.space or "",
            sub_zone_id=args.sub_zone or "",
            preparation_type=args.preparation_type or "labour",
            area_m2=args.area_m2 or 0,
            depth_cm=args.depth_cm or 0,
            soil_condition=args.soil_condition or "",
            texture=args.texture or "",
            notes=args.notes or "",
            assigned_to=args.assigned_to or "",
            start_date=args.start_date or "",
        )
        if args.json:
            print(json.dumps(sp.to_dict(), indent=2, ensure_ascii=False, default=str))
            return
        print(f"  Préparation sol créée: {sp.id} ({sp.name})")

    elif args.action == "soil-show":
        if not args.soil_prep_id:
            print("  Erreur: soil_prep_id requis")
            return
        sp = pm.get_soil_prep(args.soil_prep_id)
        if args.json:
            print(json.dumps(sp.to_dict() if sp else None,
                             indent=2, ensure_ascii=False, default=str))
            return
        if not sp:
            print(f"  Préparation {args.soil_prep_id} introuvable")
            return
        d = sp.to_dict()
        print(f"\n  Sol: {d['name']} ({d['id']})")
        for k, v in d.items():
            print(f"  | {k}: {v}")

    elif args.action == "soil-update":
        if not args.soil_prep_id:
            print("  Erreur: soil_prep_id requis")
            return
        updates = {}
        for k in ("status", "notes", "assigned_to", "soil_condition",
                   "texture", "depth_cm", "area_m2"):
            v = getattr(args, k, None)
            if v is not None:
                updates[k] = v
        sp = pm.update_soil_prep(args.soil_prep_id, **updates)
        print(f"  {'Mis à jour' if sp else 'Échec'}: {args.soil_prep_id}")

    elif args.action == "soil-amend":
        if not args.soil_prep_id:
            print("  Erreur: soil_prep_id requis")
            return
        amt = args.amendment_type or "compost"
        qty = args.quantity_kg or 0
        sp = pm.add_soil_amendment(args.soil_prep_id, amt, qty,
                                    product_name=args.product_name or "",
                                    notes=args.notes or "")
        print(f"  {'Amendement ajouté' if sp else 'Échec'}")

    elif args.action == "planting-list":
        items = pm.list_plantings(
            space_id=args.space, status=args.status,
            product_id=args.product_id)
        if args.json:
            print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
            return
        if not items:
            print("  Aucune plantation")
            return
        print(f"\n  Plantations ({len(items)})")
        for p in items:
            print(f"  {p['id']:20} {p['name']:25} {p.get('status','?'):12} "
                  f"{p.get('plant_count',0):>4} plants "
                  f"{p.get('product_name',''):20} {p.get('planting_date','')[:10]}")

    elif args.action == "planting-create":
        tp = pm.create_planting(
            name=args.name or args.sub_zone or "plantation",
            space_id=args.space or "",
            sub_zone_id=args.sub_zone or "",
            product_id=args.product_id or "",
            product_name=args.product_name or "",
            variety=args.variety or "",
            rootstock=args.rootstock or "",
            plant_count=args.plant_count or 0,
            spacing_m=args.spacing_m or 0,
            spacing_plant=args.spacing_plant or 0,
            planting_method=args.planting_method or "trou",
            planting_date=args.planting_date or "",
            notes=args.notes or "",
            assigned_to=args.assigned_to or "",
            stake_type=args.stake_type or "aucun",
            initial_watering_l=args.initial_watering_l or 0,
            mulch_type=args.mulch_type or "aucun",
            irrigation_type=args.irrigation_type or "aucun",
            hole_depth_cm=args.hole_depth_cm or 0,
            hole_width_cm=args.hole_width_cm or 0,
        )
        if args.json:
            print(json.dumps(tp.to_dict(), indent=2, ensure_ascii=False, default=str))
            return
        print(f"  Plantation créée: {tp.id} ({tp.name}) — {tp.plant_count} plants")

    elif args.action == "planting-show":
        if not args.planting_id:
            print("  Erreur: planting_id requis")
            return
        tp = pm.get_planting(args.planting_id)
        if args.json:
            print(json.dumps(tp.to_dict() if tp else None,
                             indent=2, ensure_ascii=False, default=str))
            return
        if not tp:
            print(f"  Plantation {args.planting_id} introuvable")
            return
        d = tp.to_dict()
        print(f"\n  Plantation: {d['name']} ({d['id']})")
        for k, v in d.items():
            print(f"  | {k}: {v}")

    elif args.action == "planting-update":
        if not args.planting_id:
            print("  Erreur: planting_id requis")
            return
        updates = {}
        for k in ("status", "notes", "assigned_to", "plant_count",
                   "planting_date", "variety", "rootstock"):
            v = getattr(args, k, None)
            if v is not None:
                updates[k] = v
        tp = pm.update_planting(args.planting_id, **updates)
        print(f"  {'Mis à jour' if tp else 'Échec'}: {args.planting_id}")

    elif args.action == "plan-list":
        items = pm.list_plans(
            space_id=args.space, status=args.status,
            season=args.season, year=args.year)
        if args.json:
            print(json.dumps(items, indent=2, ensure_ascii=False, default=str))
            return
        if not items:
            print("  Aucun plan de production")
            return
        print(f"\n  Plans de production ({len(items)})")
        for p in items:
            print(f"  {p['id']:20} {p['name']:25} {p.get('status','?'):10} "
                  f"{p.get('season','?'):10} {p.get('year',0)} "
                  f"{p.get('estimated_yield_kg',0):>6}kg")

    elif args.action == "plan-create":
        plan = pm.create_plan(
            name=args.name or "plan",
            space_id=args.space or "",
            sub_zone_id=args.sub_zone or "",
            product_id=args.product_id or "",
            product_name=args.product_name or "",
            season=args.season or "",
            year=args.year,
            estimated_yield_kg=args.estimated_yield_kg or 0,
            start_date=args.start_date or "",
            estimated_end_date=args.estimated_end_date or "",
            notes=args.notes or "",
        )
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False,
                             default=str))
            return
        print(f"  Plan créé: {plan.id} ({plan.name})")

    elif args.action == "plan-show":
        if not args.plan_id:
            print("  Erreur: plan_id requis")
            return
        plan = pm.get_plan(args.plan_id)
        if args.json:
            print(json.dumps(plan.to_dict() if plan else None,
                             indent=2, ensure_ascii=False, default=str))
            return
        if not plan:
            print(f"  Plan {args.plan_id} introuvable")
            return
        d = plan.to_dict()
        print(f"\n  Plan: {d['name']} ({d['id']})")
        for k, v in d.items():
            print(f"  | {k}: {v}")

    elif args.action == "plan-update":
        if not args.plan_id:
            print("  Erreur: plan_id requis")
            return
        updates = {}
        for k in ("status", "notes", "estimated_yield_kg", "season"):
            v = getattr(args, k, None)
            if v is not None:
                updates[k] = v
        plan = pm.update_plan(args.plan_id, **updates)
        print(f"  {'Mis à jour' if plan else 'Échec'}: {args.plan_id}")

    elif args.action == "stats":
        s = pm.stats()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Production Stats")
        for k, v in s.items():
            print(f"  | {k}: {v}")


def cmd_config(args):
    """Gestion de la configuration."""
    if args.action == "show":
        print(config.to_json())

    elif args.action == "set" and args.key and args.value:
        config.set(args.key, args.value)
        print(f"✅ {args.key} = {args.value}")


# ── TimescaleDB ──────────────────────────────────────────────

def cmd_tsdb(args):
    """TimescaleDB : séries temporelles, catalog, migration."""
    from core.bgdatasys import bgdatasys
    from core.tsdb import tsdb as tsdb_engine

    if args.action == "stats":
        s = bgdatasys.stats().get("tsdb", {})
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        if not s.get("connected"):
            print("  TimescaleDB: ❌ Non connecté")
            return
        print(f"\n  TimescaleDB: ✅ Connecté ({s.get('host')}:{s.get('port')})")
        print(f"  Database: {s.get('database')}")
        print(f"  Mesures: {s.get('measurements', 0)}")
        print(f"  Capteurs: {s.get('sensors_registered', 0)}")
        print(f"  Événements: {s.get('events', 0)}")
        print(f"  Training runs: {s.get('training_runs', 0)}")
        print(f"  Prédictions: {s.get('predictions', 0)}")
        if s.get("daily_counts_7d"):
            print(f"  Derniers 7j:")
            for day, count in list(s["daily_counts_7d"].items())[:7]:
                print(f"    {day}: {count} mesures")

    elif args.action == "query":
        rows = bgdatasys.query_sensors(args.space, args.sensor, args.hours)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        print(f"\n  {len(rows)} mesures ({(args.space or '*')}/{(args.sensor or '*')}, {args.hours}h)")
        for r in rows[:20]:
            ts = r.get("time", r.get("timestamp", ""))[:19]
            print(f"  {ts} | {r.get('sensor_id',''):<20} {r.get('value',''):>8} {r.get('unit','')}")
        if len(rows) > 20:
            print(f"  ... et {len(rows)-20} de plus")

    elif args.action == "write":
        if not args.sensor or args.value is None:
            print("  Erreur: --sensor et --value requis")
            return
        bgdatasys.write_measurement(
            args.space or "", args.sensor, args.value, args.unit or "")
        print(f"  Mesure écrite: {args.sensor} = {args.value} {args.unit or ''}")

    elif args.action == "hourly":
        rows = bgdatasys.hourly_avg(args.space, args.sensor, args.hours)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        print(f"\n  Moyennes horaires ({args.hours}h) — {len(rows)} buckets")
        for r in rows[:24]:
            bucket = r.get("bucket", r.get("hour", ""))[:19]
            print(f"  {bucket} | avg={r.get('avg_value',r.get('avg','')):>8} min={r.get('min_value',r.get('min','')):>8} max={r.get('max_value',r.get('max','')):>8} n={r.get('sample_count',r.get('count',0))}")

    elif args.action == "daily":
        rows = bgdatasys.daily_avg(args.space, args.sensor, args.days)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        print(f"\n  Moyennes journalières ({args.days}j) — {len(rows)} buckets")
        for r in rows[:14]:
            print(f"  {r['bucket'][:10]} | avg={r['avg_value']:>8} min={r['min_value']:>8} max={r['max_value']:>8} n={r['sample_count']}")

    elif args.action == "sensors":
        sensors = bgdatasys.list_sensors(args.space, args.stype)
        if args.json:
            print(json.dumps(sensors, indent=2, ensure_ascii=False))
            return
        print(f"\n  Capteurs enregistrés: {len(sensors)}")
        for s in sensors:
            print(f"  {s['sensor_id']:<20} {s.get('space_id',''):<15} {s.get('sensor_type',''):<15} {s.get('unit',''):<6} bus={s.get('bus','')}")

    elif args.action == "register":
        if not args.sensor:
            print("  Erreur: --sensor requis")
            return
        ok = bgdatasys.register_sensor(
            args.sensor, args.space or "", args.stype or "unknown",
            args.sensor, args.unit or "", args.bus)
        print(f"  Capteur {'enregistré' if ok else 'erreur'}: {args.sensor}")

    elif args.action == "event":
        if not args.event_type:
            print("  Erreur: --event-type requis")
            return
        bgdatasys.write_event(args.event_type, args.space or "",
                              args.sensor or "")
        print(f"  Événement créé: {args.event_type}")

    elif args.action == "events":
        events = bgdatasys.query_events(args.event_type, args.space, args.hours)
        if args.json:
            print(json.dumps(events, indent=2, ensure_ascii=False))
            return
        print(f"\n  Événements: {len(events)}")
        for e in events[:20]:
            print(f"  {e.get('time','')[:19]} | {e.get('event_type',''):<15} {e.get('space_id',''):<15} {e.get('value','')}")

    elif args.action == "migrate":
        print(f"  Migration MongoDB → TimescaleDB ({args.hours}h)...")
        result = bgdatasys.migrate_from_mongodb(args.hours)
        print(f"  Résultat: {json.dumps(result, indent=2)}")

    elif args.action == "seed":
        print(f"  Génération données de test ({args.days}j, 15min interval)...")
        result = bgdatasys.seed_test_data(args.days, 15)
        print(f"  {result.get('points_generated', 0)} points générés")

    elif args.action == "training":
        runs = bgdatasys.list_training_runs(args.model, args.limit)
        if args.json:
            print(json.dumps(runs, indent=2, ensure_ascii=False))
            return
        print(f"\n  Training runs: {len(runs)}")
        for r in runs:
            print(f"  {r.get('run_id',''):<20} {r.get('model_name',''):<20} {r.get('status',''):<12} MAE={r.get('mae','N/A')} R²={r.get('r2_score','N/A')}")

    elif args.action == "predictions":
        preds = bgdatasys.query_predictions(args.model, args.space, args.hours)
        if args.json:
            print(json.dumps(preds, indent=2, ensure_ascii=False))
            return
        print(f"\n  Prédictions: {len(preds)}")
        for p in preds[:20]:
            print(f"  {p.get('time','')[:19]} | {p.get('model_name',''):<15} pred={p.get('predicted_value','N/A'):>8} conf={p.get('confidence','N/A')}% actual={p.get('actual_value','N/A')}")


# ─── RL ────────────────────────────────────────────────────

def cmd_rl(args):
    """RL Controller - Reinforcement Learning pour irrigation/chauffage."""
    from core.rl_controller import RLController, ACTION_LABELS

    rl = RLController(args.zone)

    if args.action == "stats":
        s = rl.stats()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  RL Controller [{args.zone}]")
        print(f"  ├ States: {s['states']}")
        print(f"  ├ Q-values: {s['total_q_values']}")
        print(f"  ├ Epsilon: {s['epsilon']}")
        print(f"  ├ Alpha: {s['alpha']}  Gamma: {s['gamma']}")
        print(f"  ├ Steps: {s['steps']}")
        print(f"  ├ Memory: {s['memory_size']}/{rl.memory_size}")
        print(f"  └ Memory (disk): {s['memory_kb']} KB")

    elif args.action == "step":
        if args.moisture is None or args.temp is None:
            print("  Erreur: --moisture et --temp requis")
            return
        hour = args.hour if args.hour is not None else datetime.now().hour
        action = rl.choose_action(args.moisture, args.temp, hour)
        adj = rl.apply_action_to_geothermal(action, 50, 20)
        best = rl.get_best_action(args.moisture, args.temp, hour)
        if args.json:
            print(json.dumps({"action": int(action), "label": ACTION_LABELS[action],
                              "adjustments": adj, "best": best},
                              indent=2, ensure_ascii=False))
            return
        print(f"\n  Zone: {args.zone}  Moisture: {args.moisture}%  Temp: {args.temp}°C  Hour: {hour}h")
        print(f"  Action: {ACTION_LABELS[action]} (id={action})")
        print(f"  Adjustments: valve={adj['valve_pct']}% setpoint={adj['setpoint']}°C")
        print(f"  Best Q: {best['max_q']}  Epsilon: {rl.epsilon:.4f}")

    elif args.action == "best":
        if args.moisture is None or args.temp is None:
            print("  Erreur: --moisture et --temp requis")
            return
        hour = args.hour if args.hour is not None else datetime.now().hour
        best = rl.get_best_action(args.moisture, args.temp, hour)
        if args.json:
            print(json.dumps(best, indent=2, ensure_ascii=False))
            return
        print(f"\n  Meilleure action pour [{args.zone}]")
        print(f"  State: {best['state']}")
        print(f"  Action: {best['action_label']} (Q={best['max_q']})")
        print(f"  All Q: {[f'{l}: {q:.2f}' for l,q in zip(ACTION_LABELS.values(), best['q_values'])]}")

    elif args.action == "history":
        h = rl.history(limit=20)
        if args.json:
            print(json.dumps(h, indent=2, ensure_ascii=False))
            return
        print(f"\n  Historique RL [{args.zone}] ({len(h)} entrées)")
        for entry in h[-10:]:
            print(f"  {entry.get('ts','')[:19]} | action={entry.get('action_label','?'):<20} reward={entry.get('reward',0):>6.2f} ϵ={entry.get('epsilon',0):.3f}")

    elif args.action == "reset":
        rl.reset_epsilon()
        print(f"  Epsilon reset pour [{args.zone}]")

    elif args.action == "save":
        rl.save()
        print(f"  Q-table sauvegardee pour [{args.zone}]")


# ─── Training Scheduler ────────────────────────────────────

def cmd_train_scheduler(args):
    """Planificateur d'entrainement automatique."""
    from core.config import PixelOSConfig
    from core.mqtt import PixelOSMQTT
    cfg = PixelOSConfig()
    mqtt = PixelOSMQTT(
        broker=cfg.get("mqtt.broker", "localhost"),
        port=cfg.get("mqtt.port", 1883),
        client_id="pixelos-cli-scheduler",
    )
    mqtt.connect()
    from agent.training_scheduler import TrainingScheduler
    ts = TrainingScheduler(mqtt)

    if args.action == "check":
        reason = ts.should_train()
        if args.json:
            print(json.dumps({"should_train": reason is not None, "reason": reason},
                              indent=2, ensure_ascii=False))
            return
        if reason:
            print(f"  Entrainement necessaire: {reason}")
        else:
            print(f"  Entrainement NON necessaire")
        s = ts.stats()
        print(f"  Checks: {s['checks']}  Triggered: {s['trainings_triggered']}  Skipped: {s['trainings_skipped']}")

    elif args.action == "run":
        print(f"  Execution entrainement...")
        result = ts.run_training(force=args.force)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        status = result.get("status", "?")
        metrics = result.get("metrics", {})
        print(f"  Status: {status}")
        if metrics:
            print(f"  MAE: {metrics.get('mae')}  R²: {metrics.get('r2_score')}  Acc: {metrics.get('accuracy_pct')}%")

    elif args.action == "schedule":
        result = ts.schedule_recurring()
        print(f"  {result.get('message', 'Tache recurrente creee')}")

    elif args.action == "stats":
        s = ts.stats()
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"\n  Training Scheduler Stats")
        for k, v in s.items():
            print(f"  ├ {k}: {v}")

    mqtt.disconnect()


def cmd_dns(args):
    """Serveur DNS privé PixelOS."""
    from core.dns import PixelDNSServer
    from core.config import PixelOSConfig

    cfg = PixelOSConfig()
    dns_cfg = cfg.get("dns", {})
    server = PixelDNSServer(dns_cfg)

    if args.action == "start":
        try:
            server.start()
            print(f"  DNS démarré sur port {dns_cfg.get('port', 5353)}")
            print(f"  TLD: .{dns_cfg.get('domain', 'pxl')}")
            print(f"  Forwarder: {dns_cfg.get('forwarder', '8.8.8.8')}")
            if args.json:
                import json as _json
                print(_json.dumps(server.status(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"  Échec démarrage DNS: {e}")

    elif args.action == "stop":
        server.stop()
        print("  DNS arrêté")

    elif args.action == "status" or args.action == "restart":
        if args.action == "restart":
            server.stop()
            server.start()
            print("  DNS redémarré")
        status = server.status()
        if args.json:
            import json as _json
            print(_json.dumps(status, indent=2, ensure_ascii=False))
            return
        running = "✓ En cours" if status["running"] else "✗ Arrêté"
        print(f"  Statut: {running}")
        print(f"  Port: {status['port']}")
        print(f"  TLD: .{status['tld']}")
        print(f"  Requêtes: {status['stats']['queries']}")
        print(f"  Répondues: {status['stats']['answered']}")
        print(f"  Forwardées: {status['stats']['forwarded']}")
        print(f"  Erreurs: {status['stats']['errors']}")
        print(f"  Enregistrements:")
        for name, ip in status["records"].items():
            print(f"    {name} → {ip}")

    elif args.action == "records":
        status = server.status()
        if args.json:
            import json as _json
            print(_json.dumps(status["records"], indent=2, ensure_ascii=False))
            return
        print(f"  Enregistrements DNS ({status['domain']}):")
        for name, ip in status["records"].items():
            print(f"    {name} → {ip}")


def cmd_federation(args):
    """Réseau fédéré PixelOS — biodiversité mondiale."""
    from core.federation.node import node_manager as nm
    from core.federation.biodiversity import biodiversity_registry as br

    if args.action == "status":
        st = nm.federation_status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"\n  Réseau Fédéré PixelOS")
        print(f"  Node ID  : {st['node_id']}")
        print(f"  Nom      : {st['nickname']}")
        print(f"  Clé      : {st['public_key']}")
        print(f"  Pairs    : {st['peers_known']} connus, {st['peers_online']} en ligne")

    elif args.action == "announce":
        ann = nm.announce()
        if args.json:
            print(json.dumps(ann, indent=2, ensure_ascii=False))
            return
        print(f"  Annonce publiée pour {ann['node_id']} ({ann['nickname']})")
        print(f"  Biodiversité: {ann.get('biodiversity', {}).get('total', 0)} espèces")

    elif args.action == "peers":
        peers = nm.list_peers()
        if args.json:
            print(json.dumps(peers, indent=2, ensure_ascii=False))
            return
        print(f"\n  Pairs ({len(peers)}):")
        for p in peers:
            print(f"  {p['node_id']:<20} {p.get('nickname',''):<20} "
                  f"IP: {p.get('ip_vpn',''):<15} Région: {p.get('region','')}")

    elif args.action == "species":
        query = args.query or ""
        status = args.status or ""
        if status:
            results = br.list_by_status(status)
        elif query:
            results = br.search(query)
        else:
            results = []
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return
        print(f"\n  Espèces ({len(results)}):")
        for r in results:
            cons = r.get("conservation", {})
            icon = {"gravement_menacee":"CR","menacee":"EN","vulnerable":"VU",
                    "preoccupation_mineure":"LC"}.get(cons.get("status",""), "??")
            print(f"  [{icon}] {r.get('nom_scientifique',''):<35} "
                  f"{r.get('nom_commun',''):<20} {r.get('origine',{}).get('region','')}")

    elif args.action == "species-create":
        from core.federation.biodiversity import BiodiversityRecord, ConservationRecord, Geolocation, CultivationProfile
        record = BiodiversityRecord(
            nom_scientifique=args.scientific_name or "",
            nom_commun=args.common_name or "",
            famille=args.family or "",
            genre=args.genus or "",
            type_race=args.race_type or "locale",
            confidentialite=args.confidentiality or "public",
            conservation=ConservationRecord(
                status=args.conservation_status or "non_evaluee",
                source=args.conservation_source or ""
            ),
            origine=Geolocation(
                latitude=args.latitude or 0.0,
                longitude=args.longitude or 0.0,
                region=args.region or "",
                pays=args.country or "",
                biome=args.biome or ""
            ),
            cultivation=CultivationProfile(
                besoin_eau=args.water_need or "moyen"
            ),
            createur_id=nm.identity.node_id,
            date_creation=datetime.now().isoformat(),
        )
        fp = br.save(record)
        print(f"  Espèce enregistrée: {record.nom_scientifique}")
        print(f"  Fingerprint: {fp}")

    elif args.action == "mesh-status":
        from core.federation.mesh import wireguard_mesh
        st = wireguard_mesh.mesh_status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"\n  Réseau Mesh WireGuard")
        print(f"  Interface : {st['interface']}")
        print(f"  Réseau    : {st['network']}")
        print(f"  Pairs     : {st['peers_online']}/{st['peers_total']} en ligne")
        for p in st["peers"]:
            icon = "🟢" if p["online"] else "🔴"
            print(f"  {icon} {p['node_id'][:12]}  {p.get('endpoint',''):<25} {p.get('label','')}")

    elif args.action == "mesh-connect":
        from core.federation.mesh import wireguard_mesh
        r = wireguard_mesh.init_mesh(nm.identity.node_id)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Mesh initialisé: {r['address']}")
        print(f"  Clé publique: {r['public_key']}")
        for found in nm.discover_peers_dht():
            print(f"  Pair potentiel: {found['ip']}")

    elif args.action == "gov-status":
        from core.federation.governance import governance
        st = governance.governance_status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"\n  Gouvernance PixelOS")
        print(f"  Membres    : {st['members']}")
        print(f"  Validateurs: {st['validators']}")
        print(f"  Propositions: {st['proposals_open']} ouvertes, "
              f"{st['proposals_approved']} approuvées, {st['proposals_rejected']} rejetées")
        print(f"  Consensus  : {st['consensus_threshold']} en {st['voting_period_h']}h")

    elif args.action == "gov-register":
        from core.federation.governance import governance
        m = governance.register_member(
            node_id=nm.identity.node_id,
            public_key=nm.identity.public_key,
            nickname=args.name or nm.identity.nickname,
            country=args.country or "",
            region=args.region or "",
        )
        if args.json:
            print(json.dumps(m, indent=2, ensure_ascii=False))
            return
        print(f"  Enregistré: {m.nickname} ({m.node_id[:16]}...) rôle: {m.role}")

    elif args.action == "gov-propose":
        from core.federation.governance import governance
        prop = governance.create_proposal(
            title=args.query or "Proposition",
            description=args.description or "",
            proposal_type=getattr(args, 'type', 'update'),
            proposer_id=nm.identity.node_id,
        )
        if args.json:
            print(json.dumps(prop, indent=2, ensure_ascii=False))
            return
        print(f"  Proposition créée: {prop.proposal_id}")
        print(f"  Titre: {prop.title}")
        print(f"  Vote jusqu'au: {prop.deadline[:16]}")

    elif args.action == "gov-vote":
        from core.federation.governance import governance
        r = governance.vote(
            proposal_id=args.proposal_id or "",
            node_id=nm.identity.node_id,
            vote=getattr(args, 'vote', True),
        )
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Vote enregistré: {r['vote']} sur {r['proposal_id']}")

    elif args.action == "discover":
        found = nm.discover_peers_dht()
        if args.json:
            print(json.dumps(found, indent=2))
            return
        print(f"  Scan réseau: {len(found)} pairs découverts")
        for f in found:
            print(f"  {f['ip']}")


def cmd_ftp(args):
    """Gestion FTP zones agricoles."""
    from core.ftp import ftp_manager as fm

    if args.action == "zones":
        st = fm.status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"\n  Zones FTP ({st['total_zones']}):")
        for z in st["zones"]:
            print(f"  {z['user']:<25} {z['path']}")
        print(f"\n  Base: {st['base_path']}")

    elif args.action == "create":
        if not args.zone:
            print("  Erreur: --zone requis")
            return
        r = fm.create_zone(args.zone)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  {r['status']}: {r.get('message', r['zone'])}")
        if r.get("user"):
            print(f"  Utilisateur: {r['user']}")
            print(f"  Path: {r['path']}")

    elif args.action == "delete":
        if not args.zone:
            print("  Erreur: --zone requis")
            return
        r = fm.delete_zone(args.zone)
        print(f"  {r['status']}: zone {r['zone']} supprimée")


def cmd_vpn(args):
    """VPN WireGuard PixelOS (comme Tailscale)."""
    from core.vpn import vpn_manager as vm

    if args.action in ("ip", "ips"):
        print(f"  {vm.status()['tunnel']['server_ip']}")
        for c in vm.list_clients():
            print(f"  {c['ip']}")
        return

    if args.action == "up":
        args.action = "start-all"

    if args.action == "down":
        args.action = "stop-all"

    if args.action in ("autostart",):
        import subprocess, sys, os
        from pathlib import Path
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        vbs_path = startup / "pixelos-vpn.vbs"
        if args.sub == "disable":
            if vbs_path.exists():
                vbs_path.unlink()
                print("  Autostart VPN désactivé")
            else:
                print("  Pas d'autostart actif")
            return
        # Enable: create VBS script in Startup folder
        pixelos_cli = shutil.which("pixelos") or sys.executable + " -m cli.main"
        vbs_content = (
            f'Set shell = CreateObject("WScript.Shell")\n'
            f'shell.Run "{pixelos_cli} vpn start-all", 0, False\n'
        )
        vbs_path.write_text(vbs_content)
        print(f"  Autostart VPN active -> {vbs_path}")
        # Also try to install tunnel if not done
        r = vm.install_tunnel()
        if r.get("status") in ("ok", "elevate"):
            print(f"  Tunnel: {r['message']}")
        return

    if args.action == "status":
        st = vm.status(full=args.full)
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        tun_icon = "RUN" if st["tunnel_running"] else "STOP"
        fwd_icon = "RUN" if st["forwarder"]["running"] else "STOP"
        print(f"\n  VPN PixelOS")
        print(f"  Tunnel:{tun_icon:>6}  {st['tunnel']['name']} ({st['tunnel']['server_ip']}/24 port {st['tunnel']['port']})")
        print(f"  DNS Forwarder:{fwd_icon:>6}  {st['forwarder']['listen']} -> {st['forwarder']['forward']}")
        print(f"  Installé: {'OUI' if st['tunnel_installed'] else 'NON'}")
        if st.get("server_public_key"):
            print(f"  Clé publique: {st['server_public_key']}")
        print(f"  Clients: {st['client_configs']}")
        for c in st.get("clients", []):
            print(f"    {c['file']}")
        if st["tunnel"].get("wg_show"):
            print(f"\n  Interface:\n{st['tunnel']['wg_show']}")

    elif args.action == "start":
        r = vm.start()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        if r.get("status") == "elevate":
            print(f"  ⚠ {r['message']}")
            print(f"  Lance en Administrateur : pixelos vpn {args.action}")
            return
        for svc, res in r.items():
            icon = "OK" if res["status"] == "ok" else "KO"
            print(f"  [{icon}] {svc}: {res['message']}")

    elif args.action == "start-all":
        r = vm.start_all()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for svc, res in r.items():
            icon = "OK" if res["status"] == "ok" else "KO"
            print(f"  [{icon}] {svc}: {res['message']}")

    elif args.action == "stop-all":
        r = vm.stop_all()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for svc, res in r.items():
            icon = "OK" if res["status"] == "ok" else "KO"
            print(f"  [{icon}] {svc}: {res['message']}")

    elif args.action == "stop":
        r = vm.stop()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for svc, res in r.items():
            icon = "OK" if res["status"] == "ok" else "KO"
            print(f"  [{icon}] {svc}: {res['message']}")

    elif args.action == "restart":
        r = vm.restart()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        for svc, res in r.items():
            icon = "OK" if res["status"] == "ok" else "KO"
            print(f"  [{icon}] {svc}: {res['message']}")

    elif args.action == "install":
        r = vm.install_tunnel()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  {r['status']}: {r['message']}")

    elif args.action == "uninstall":
        r = vm.uninstall_tunnel()
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  {r['status']}: {r['message']}")

    elif args.action == "client":
        r = vm.gen_client_config(
            client_name=args.name or "client",
            server_endpoint=args.endpoint or "196.179.160.78:51820",
        )
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"\n  Client créé: {r['client_name']}")
        print(f"  IP: {r['client_ip']}")
        print(f"  Config: {r['config_file']}")
        print(f"  Clé publique: {r['public_key']}")
        print(f"\n  --- Config client ---")
        print(r["config"])

    elif args.action == "clients":
        clients = vm.list_clients()
        if args.json:
            print(json.dumps(clients, indent=2, ensure_ascii=False))
            return
        print(f"\n  Clients WireGuard ({len(clients)})")
        for c in clients:
            print(f"  {c['file']:<30} {c['ip']}")

    elif args.action == "forwarder":
        if args.sub == "start":
            r = vm.forwarder.start()
            print(f"  {r['status']}: {r['message']}")
        elif args.sub == "stop":
            r = vm.forwarder.stop()
            print(f"  {r['status']}: {r['message']}")
        elif args.sub == "status":
            st = vm.forwarder.status()
            print(f"  DNS Forwarder: {'RUN' if st['running'] else 'STOP'}")
            print(f"  {st['listen']} -> {st['forward']}")


def cmd_update(args):
    """Mise à jour de PixelOS."""
    from core.updater import UpdateManager

    um = UpdateManager()

    if args.mode == "check":
        info = um.check()
        if args.json:
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return
        print(f"\n  PixelOS {info['current_version']}")
        print(f"  Mode: {info['mode']}  Path: {info['install_path']}")
        if "git_commit" in info:
            print(f"  Git: {info['git_commit']}")
        if info.get("usb_available"):
            print(f"  USB détectée: {info['usb_available']}")

    elif args.mode == "history":
        hist = um.history()
        if args.json:
            print(json.dumps(hist, indent=2, ensure_ascii=False))
            return
        if not hist:
            print("  Aucun historique")
            return
        print(f"\n  Historique ({len(hist)} entrées)")
        for h in reversed(hist):
            print(f"  [{h['ts'][:19]}] {h['version']} mode={h['mode']} {h.get('status','?')}")

    elif args.mode == "rollback":
        result = um.rollback(args.version)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        if result["status"] == "ok":
            print(f"  Rollback effectué: {result['backup']}")
        else:
            print(f"  Échec: {result.get('message', '?')}")

    else:
        result = um.update(mode=args.mode)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        for k, v in result.items():
            if isinstance(v, dict) and "status" in v:
                icon = "✓" if v["status"] == "ok" else "✗"
                msg = v.get("message", v.get("version", v.get("status", "?")))
                print(f"  {icon} {k}: {msg}")
        if "new_version" in result:
            print(f"\n  Version: {result['new_version']}")


def cmd_ipfs(args):
    """Stockage décentralisé IPFS pour PixelOS."""
    from core.federation.ipfs_store import ipfs_store

    if args.action == "status":
        st = ipfs_store.status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        if not st.get("available"):
            print(f"  IPFS: {st.get('message', 'Non disponible')}")
            return
        print(f"  IPFS: {'✅' if st.get('available') else '❌'}")
        print(f"  Peer ID: {st.get('peer_id', 'N/A')}")
        print(f"  Pinnés: {st.get('pinned', 0)} publications")

    elif args.action == "init":
        r = ipfs_store.init_repo()
        print(f"  {r['status']}: {r.get('message', 'OK')}")

    elif args.action == "start":
        r = ipfs_store.start_daemon()
        print(f"  {r['status']}: {r.get('message', 'OK')}")

    elif args.action == "stop":
        r = ipfs_store.stop_daemon()
        print(f"  {r['status']}: {r.get('message', 'OK')}")

    elif args.action == "publish":
        from core.federation.biodiversity import biodiversity_registry
        from core.federation.node import node_manager
        records = biodiversity_registry.search("")
        pub = ipfs_store.publish_biodiversity(
            records, node_id=node_manager.identity.node_id)
        if args.json:
            print(json.dumps(pub, ensure_ascii=False) if pub else '{"status":"error"}')
            return
        if pub:
            print(f"  Publié sur IPFS: {pub.cid}")
            print(f"  IPNS: {pub.ipns or 'N/A'}")
            print(f"  Enregistrements: {pub.record_count}")
        else:
            print("  Erreur publication IPFS")

    elif args.action == "fetch":
        if not args.cid:
            print("  Erreur: CID requis")
            return
        data = ipfs_store.fetch_biodiversity(args.cid)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("  CID introuvable sur le réseau IPFS")

    elif args.action == "sync":
        from core.federation.bootstrap import bootstrap_portal
        seeds = bootstrap_portal.get_seed_nodes()
        bootstrap_addrs = [s.get("address", "") for s in seeds if s.get("address")]
        records = ipfs_store.sync_global_registry(bootstrap_addrs)
        print(f"  Synchronisé: {len(records)} enregistrements depuis {len(bootstrap_addrs)} nœuds")


def cmd_matrix(args):
    """Messagerie temps réel communauté Matrix."""
    from core.federation.matrix_bridge import matrix_bridge

    if args.action == "status":
        st = matrix_bridge.status()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"  Matrix: {'✅ Connecté' if st['enabled'] else '❌ Non configuré'}")
        print(f"  Serveur: {st['homeserver']}")
        print(f"  Utilisateur: {st['user_id']}")
        print(f"  Salon général: {st['room_main']}")

    elif args.action == "configure":
        r = matrix_bridge.configure(
            homeserver=args.homeserver or "",
            user_id=args.user or "",
            access_token=args.token or "",
            room=args.room or "",
        )
        print(f"  {'✅' if r['enabled'] else '❌'} Matrix {'configuré' if r['enabled'] else 'déconnecté'}")

    elif args.action == "test":
        if not matrix_bridge.config.enabled:
            print("  Matrix non configuré. D'abord: pixelos matrix configure ...")
            return
        ok = matrix_bridge.notify_alert(
            "🧪 Test PixelOS Bot",
            "Ceci est un message de test depuis votre nœud PixelOS",
            severity="info",
        )
        print(f"  {'✅ Message envoyé' if ok else '❌ Échec envoi'}")


def cmd_portal(args):
    """Portail communauté PixelOS."""
    from core.federation.bootstrap import bootstrap_portal
    from core.federation.node import node_manager

    if args.action == "status":
        st = bootstrap_portal.community_stats()
        if args.json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return
        print(f"\n  Communauté PixelOS — Portail")
        print(f"  Nœuds seed: {st['total_nodes']}")
        print(f"  Pays: {st['total_countries']}")
        print(f"  En ligne: {st['online_nodes']}")
        print(f"  ISO: {st.get('iso_url', 'N/A')}")
        print(f"  Miroirs disponibles: {len(st.get('mirrors', []))}")
        for m in st.get("mirrors", []):
            print(f"    {m['name']:<30} {m['url']} [{m['country']}]")

    elif args.action == "register-seed":
        bootstrap_portal.node.node_id = node_manager.identity.node_id
        bootstrap_portal.node.public_key = node_manager.identity.public_key
        if args.country:
            bootstrap_portal.node.country = args.country
        if args.nickname:
            bootstrap_portal.node.nickname = args.nickname
        r = bootstrap_portal.register_seed()
        print(f"  {r['status']}: {r['message']}")

    elif args.action == "join":
        r = bootstrap_portal.join_request(
            nickname=args.nickname or "",
            email=args.email or "",
            country=args.country or "",
            reason=args.reason or "",
        )
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        print(f"  Demande enregistrée: {r['node_id']}")
        print(f"  Statut: {r['status']}")

    elif args.action == "mirror-add":
        if not args.name or not args.url:
            print("  Erreur: --name et --url requis")
            return
        r = bootstrap_portal.add_mirror(
            name=args.name, url=args.url,
            country=args.country or "",
        )
        print(f"  Miroir ajouté: {r['count']} miroirs disponibles")

    elif args.action == "iso-url":
        url = bootstrap_portal.get_iso_url()
        if args.json:
            print(json.dumps({"url": url}))
            return
        print(f"  Télécharger ISO: {url}")


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

def _check_tsdb() -> tuple[bool, str]:
    try:
        from core.tsdb import tsdb
        ok = tsdb.connect()
        if ok:
            return True, "Connecté"
        return False, "Non connecté"
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

    # plante
    p = sub.add_parser("plante", help="Base de donnees agronomique")
    p.add_argument("action", choices=["list", "search", "info", "categorie",
                                      "maladies", "calendrier", "irrigation"])
    p.add_argument("query", nargs="?", help="Nom de plante ou ID")
    p.add_argument("--categorie", "-c", help="Filtrer par categorie")
    p.add_argument("--cycle", help="Cycle (annuel, perenne...)")
    p.add_argument("--besoin-eau", help="besoin_eau (faible, moyen, eleve)")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_plante)

    # device
    p = sub.add_parser("device", help="Catalogue et découverte de dispositifs IoT")
    p.add_argument("action", choices=["list", "show", "register", "update", "delete",
                                      "provision", "activate", "retire",
                                      "scan-wifi", "scan-ble", "scan-all",
                                      "fingerprint", "stats"])
    p.add_argument("device_id", nargs="?", help="ID du dispositif")
    p.add_argument("--protocol", choices=["wifi", "ble", "radio", "modbus"], help="Protocole")
    p.add_argument("--status", choices=["discovered", "fingerprinted", "provisioned", "active", "retired"],
                   help="Filtrer par statut")
    p.add_argument("--space", help="Espace/zone")
    p.add_argument("--device-type", help="Type de dispositif")
    p.add_argument("--fingerprint", help="Fingerprint (MAC, UUID, adresse Modbus)")
    p.add_argument("--manufacturer", help="Fabricant")
    p.add_argument("--model", help="Modèle")
    p.add_argument("--sensor-type", help="Type de capteur (temperature, humidity...)")
    p.add_argument("--ip", help="Adresse IP")
    p.add_argument("--mac", help="Adresse MAC")
    p.add_argument("--signal", type=int, default=0, help="Force signal RSSI")
    p.add_argument("--battery", type=float, default=100.0, help="Niveau batterie %")
    p.add_argument("--meta", help="Métadonnées JSON")
    p.add_argument("--timeout", type=int, default=15, help="Timeout scan (s)")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_device)

    # service
    p = sub.add_parser("service", help="Gestion des services PixelOS")
    p.add_argument("action", choices=["status", "start", "stop", "restart",
                                      "logs", "health", "autostart"])
    p.add_argument("name", nargs="?", default=None,
                   help="Service: mysql, mongodb, mosquitto, backend, dashboard, pixelos-web, all")
    p.add_argument("--tail", type=int, default=50, help="Nombre de lignes de logs")
    p.add_argument("--json", action="store_true", help="Sortie JSON")
    p.set_defaults(func=cmd_service)

    # harvest
    p = sub.add_parser("harvest", help="Recolte: prevision, lots, etiquettes, inventaire")
    p.add_argument("action", choices=["predict", "lines", "batches", "harvest",
                                      "labels", "inventory", "suggestions"])
    p.add_argument("--line-id", help="ID de la ligne de production")
    p.add_argument("--weight", type=float, help="Poids recolte (kg)")
    p.add_argument("--price", type=float, help="Prix unitaire par kg")
    p.add_argument("--quality", choices=["A","B","C","D"], default="A")
    p.add_argument("--date", help="Date de recolte (YYYY-MM-DD)")
    p.add_argument("--status", help="Filtrer lots par status")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_harvest)

    # onnx
    p = sub.add_parser("onnx", help="Export ONNX et inference du modele ML")
    p.add_argument("action", choices=["stats", "export", "predict"])
    p.add_argument("--model", default="irrigation_model", help="Nom du modele")
    p.add_argument("--humidity", type=float, help="Humidite sol actuelle")
    p.add_argument("--temp", type=float, help="Temperature actuelle")
    p.add_argument("--hum", type=float, help="Humidite air actuelle")
    p.add_argument("--pression", type=float, help="Pression atmospherique")
    p.add_argument("--no-quant", action="store_true", help="Desactiver quantification")
    p.set_defaults(func=cmd_onnx)

    # pipeline
    p = sub.add_parser("pipeline", help="Pipeline auto-retrain ML (declenche par TaskManager)")
    p.add_argument("action", choices=["run", "versions", "rollback"])
    p.add_argument("--model", default="irrigation_model", help="Nom du modele")
    p.add_argument("--zone", default="sol_serre", help="Zone d'entrainement")
    p.add_argument("--days", type=int, default=30, help="Jours d'historique")
    p.add_argument("--force", action="store_true", help="Forcer entrainement")
    p.add_argument("--task-id", help="ID tache declencheuse pour notification")
    p.add_argument("--version", help="Version a restaurer (rollback)")
    p.set_defaults(func=cmd_pipeline)

    # web
    p = sub.add_parser("web", help="Lancer l'interface web PixelOS")
    p.add_argument("--port", type=int, default=9999, help="Port (defaut 9999)")
    p.add_argument("--debug", action="store_true", help="Mode debug Flask")
    p.set_defaults(func=cmd_web)

    # geothermal
    p = sub.add_parser("geothermal", help="Controle geothermique (PID, sondes, vannes)")
    p.add_argument("action", choices=["status", "zones", "set", "cycle", "anomalies"])
    p.add_argument("zone", nargs="?", help="ID de la zone")
    p.add_argument("--target", "-t", type=float, help="Temperature cible")
    p.add_argument("--hysteresis", type=float, help="Hysteresis en C")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_geothermal)

    # energy
    p = sub.add_parser("energy", help="Supervision energetique (solaire, batterie, charges)")
    p.add_argument("action", choices=["status", "devices", "solar", "battery", "load", "cycle", "forecast"])
    p.add_argument("load_id", nargs="?", help="ID de la charge (pour load)")
    p.add_argument("--state", "-s", choices=["on", "off", "throttle"], default="on",
                   help="Etat de la charge")
    p.add_argument("--throttle", "-t", type=float, help="Pourcentage de throttle (0-100)")
    p.add_argument("--hours", type=int, default=24, help="Heures de prevision")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_energy)

    # space
    p = sub.add_parser("space", help="Gestion des espaces (serres, pepinieres, champs)")
    p.add_argument("action", choices=["list", "show", "sensors", "control",
                                      "assign", "add", "auto", "auto-cycle"])
    p.add_argument("espace_id", nargs="?", help="ID de l'espace")
    p.add_argument("target", nargs="?", help="ID du control ou sous-zone")
    p.add_argument("--state", choices=["on", "off", "pwm", "auto_on", "auto_off"],
                   default="on", help="Etat du control")
    p.add_argument("--value", type=float, help="Valeur PWM (0-100)")
    p.add_argument("--product-id", help="ID du produit a assigner")
    p.add_argument("--planted-at", help="Date de plantation (YYYY-MM-DD)")
    p.add_argument("--type", help="Type d'espace (serre, pepiniere, plein_champ, verger)")
    p.add_argument("--label", help="Label de l'espace")
    p.add_argument("--location", help="Localisation")
    p.add_argument("--description", help="Description")
    p.add_argument("--confirm", action="store_true", help="Confirmer ajout/suppression")
    p.add_argument("--auto-type", choices=["irrigation", "climate", "light"],
                   help="Type d'auto-controle")
    p.add_argument("--enabled", type=bool, default=True, help="Activer/desactiver auto")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_space)

    # lifecycle
    p = sub.add_parser("lifecycle", help="Cycles de vie des produits agricoles")
    p.add_argument("action", choices=["products", "plantations", "plant", "tasks",
                                      "suggestions", "harvest"])
    p.add_argument("product_id", nargs="?", help="ID du produit")
    p.add_argument("plantation_id", nargs="?", help="ID de la plantation")
    p.add_argument("--espace", help="ID de l'espace")
    p.add_argument("--sub-zone", help="ID de la sous-zone")
    p.add_argument("--quantity", type=int, default=1, help="Quantite")
    p.add_argument("--label", help="Etiquette")
    p.add_argument("--planted-at", help="Date de plantation (YYYY-MM-DD)")
    p.add_argument("--force", action="store_true", help="Forcer regeneration taches")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_lifecycle)

    # tasks
    p = sub.add_parser("task", help="Gestion des taches agricoles")
    p.add_argument("action", choices=["list", "show", "create", "edit",
                                      "delete", "stats", "alerts"])
    p.add_argument("task_id", nargs="?", help="ID de la tache")
    p.add_argument("--title", "-t", help="Titre de la tache")
    p.add_argument("--description", "-d", help="Description")
    p.add_argument("--categorie", "-c", help="Categorie (plantation, irrigation, recolte, traitement, maintenance, observation, administration, autre)")
    p.add_argument("--priorite", "-p", help="Priorite (low, medium, high, urgent)")
    p.add_argument("--status", "-s", help="Statut (todo, in_progress, done, cancelled)")
    p.add_argument("--echeance", "-e", help="Echeance (YYYY-MM-DD)")
    p.add_argument("--assigne", "-a", help="Personne assignee")
    p.add_argument("--zone", "-z", help="Zone agricole")
    p.add_argument("--plante", help="Plante associee")
    p.add_argument("--query", "-q", help="Recherche")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_tasks)

    # program
    p = sub.add_parser("program", help="Programmes Text/Audio/Video")
    p.add_argument("program", choices=["text", "audio", "video"])
    p.add_argument("action", choices=["list", "show", "create", "edit", "delete", "add"])
    p.add_argument("--note-id", help="ID de la note")
    p.add_argument("--audio-id", help="ID de l'audio")
    p.add_argument("--video-id", help="ID de la video")
    p.add_argument("--title", "-t", help="Titre")
    p.add_argument("--content", "-c", help="Contenu de la note")
    p.add_argument("--categorie", help="Categorie (general, observation, technique, recolte)")
    p.add_argument("--source", "-s", help="URL ou chemin video/audio")
    p.add_argument("--duration", type=int, default=0, help="Duree en secondes")
    p.add_argument("--type", help="Type de source (url, youtube, file)")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_program)

    # lab
    p = sub.add_parser("lab", help="Pôle laboratoire: sol, microbiome, microscopie, croissance, génétique")
    p.add_argument("action", choices=["samples", "sample-create", "sample-get",
                                      "soil", "microbiome", "microscopy",
                                      "growth", "genetics", "heatmap", "stats"])
    p.add_argument("sub", nargs="?", choices=["create", "get", "track", "record", "summary"])
    p.add_argument("sample_id", nargs="?", help="ID échantillon")
    p.add_argument("plant_id", nargs="?", help="ID plante")
    p.add_argument("obs_id", nargs="?", help="ID observation microscopique")
    p.add_argument("--sample-type", help="Type échantillon (sol, eau, tissu, microbe, adn)")
    p.add_argument("--source", help="Source de l'échantillon")
    p.add_argument("--location", help="Localisation")
    p.add_argument("--collector", help="Collecteur")
    p.add_argument("--depth", type=float, help="Profondeur (cm)")
    p.add_argument("--mass", type=float, help="Masse (g)")
    p.add_argument("--notes", help="Notes")
    p.add_argument("--status", "-s", help="Statut échantillon")
    p.add_argument("--ph", type=float, help="pH du sol")
    p.add_argument("--mo", type=float, help="Matière organique (%)")
    p.add_argument("--n", type=float, help="Azote total (%)")
    p.add_argument("--p", type=float, help="Phosphore (mg/kg)")
    p.add_argument("--k", type=float, help="Potassium (mg/kg)")
    p.add_argument("--cec", type=float, help="CEC (meq/100g)")
    p.add_argument("--fe", type=float, help="Fer (mg/kg)")
    p.add_argument("--mn", type=float, help="Manganèse (mg/kg)")
    p.add_argument("--zn", type=float, help="Zinc (mg/kg)")
    p.add_argument("--soil-type", help="Type de sol")
    p.add_argument("--texture", help="Texture du sol")
    p.add_argument("--conductivite", type=float, help="Conductivité (µS/cm)")
    p.add_argument("--date", help="Date analyse")
    p.add_argument("--method", help="Méthode microbiome")
    p.add_argument("--bacteria", type=float, help="Bactéries totales (CFU/g)")
    p.add_argument("--fungi", type=float, help="Champignons totaux (CFU/g)")
    p.add_argument("--shannon", type=float, help="Indice Shannon bactéries")
    p.add_argument("--f-shannon", type=float, help="Indice Shannon champignons")
    p.add_argument("--mag", type=int, help="Grossissement microscopique")
    p.add_argument("--stain", help="Coloration")
    p.add_argument("--product-id", help="ID produit")
    p.add_argument("--stage", help="Stade phénologique")
    p.add_argument("--height", type=float, help="Hauteur (cm)")
    p.add_argument("--leaf-count", type=int, help="Nombre de feuilles")
    p.add_argument("--leaf-area", type=float, help="Surface foliaire (cm²)")
    p.add_argument("--stem-diameter", type=float, help="Diamètre tige (mm)")
    p.add_argument("--root-length", type=float, help="Longueur racine (cm)")
    p.add_argument("--branching", type=int, help="Nombre ramifications")
    p.add_argument("--spad", type=float, help="Chlorophylle SPAD")
    p.add_argument("--ndvi", type=float, help="NDVI")
    p.add_argument("--species", help="Espèce")
    p.add_argument("--variety", help="Variété")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_lab)

    # omics
    p = sub.add_parser("omics", help="Bioinformatique: séquences, alignement, phylogénie, métagénomique")
    p.add_argument("action", choices=["genomes", "import", "align", "phylogeny", "metagenomics", "stats"])
    p.add_argument("sub", nargs="?", help="Sous-action (classify, diversity)")
    p.add_argument("fasta", nargs="?", help="Fichier FASTA")
    p.add_argument("--fasta1", help="Fichier FASTA 1 (alignement)")
    p.add_argument("--fasta2", help="Fichier FASTA 2 (alignement)")
    p.add_argument("--alignment", help="Fichier d'alignement")
    p.add_argument("--method", choices=["nj", "upgma"], default="nj", help="Méthode phylogénie")
    p.add_argument("--species", help="Espèce")
    p.add_argument("--variety", help="Variété")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_omics)

    # ontology
    p = sub.add_parser("ontology", help="Ontologie agricole: profils plantes, échanges inter-systèmes")
    p.add_argument("action", choices=["traits", "trait-create", "trait-get",
                                      "compare", "export", "exchanges", "stats"])
    p.add_argument("species_id", nargs="?", help="ID espèce")
    p.add_argument("species_a", nargs="?", help="ID espèce A (comparaison)")
    p.add_argument("species_b", nargs="?", help="ID espèce B (comparaison)")
    p.add_argument("--scientific-name", help="Nom scientifique")
    p.add_argument("--common-name", help="Nom commun")
    p.add_argument("--family", help="Famille")
    p.add_argument("--genus", help="Genre")
    p.add_argument("--origin", help="Région d'origine")
    p.add_argument("--koppen", help="Zones Köppen (séparées par virgules)")
    p.add_argument("--direction", choices=["sent", "received"], help="Direction échange")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_ontology)

    # vision
    p = sub.add_parser("vision", help="Vision par ordinateur: segmentation, croissance, NDVI, racines, maladies")
    p.add_argument("action", choices=["segment", "growth", "ndvi", "root",
                                      "disease", "height", "leaf-area", "stats"])
    p.add_argument("image", nargs="?", help="Chemin image")
    p.add_argument("--nir", help="Image NIR (NDVI)")
    p.add_argument("--red", help="Image Rouge (NDVI)")
    p.add_argument("--images", help="Liste d'images séparées par virgules")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_vision)

    # tsdb
    p = sub.add_parser("tsdb", help="TimescaleDB: séries temporelles, catalog, migration")
    p.add_argument("action", choices=["stats", "query", "write", "hourly", "daily",
                                      "sensors", "register", "event", "events",
                                      "migrate", "seed", "training", "predictions"])
    p.add_argument("--sensor", help="ID du capteur")
    p.add_argument("--space", help="ID de l'espace")
    p.add_argument("--hours", type=int, default=24, help="Période en heures")
    p.add_argument("--days", type=int, default=7, help="Période en jours")
    p.add_argument("--value", type=float, help="Valeur à écrire")
    p.add_argument("--unit", default="", help="Unité de mesure")
    p.add_argument("--type", dest="stype", help="Type de capteur")
    p.add_argument("--bus", default="simulation", help="Bus de communication")
    p.add_argument("--event-type", dest="event_type", help="Type d'événement")
    p.add_argument("--model", help="Nom du modèle ML")
    p.add_argument("--limit", type=int, default=20, help="Limite résultats")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_tsdb)

    # rl
    p = sub.add_parser("rl", help="RL: reinforcement learning irrigation/chauffage")
    p.add_argument("action", choices=["stats", "step", "best", "history", "reset", "save"])
    p.add_argument("--zone", default="serre_a", help="Zone du controleur RL")
    p.add_argument("--moisture", type=float, help="Humidite sol %")
    p.add_argument("--temp", type=float, help="Temperature °C")
    p.add_argument("--hour", type=int, help="Heure (0-23)")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_rl)

    # update
    p = sub.add_parser("update", help="Mise à jour de PixelOS (git/usb/pip)")
    p.add_argument("mode", nargs="?", choices=["auto", "git", "usb", "pip", "check", "history", "rollback"],
                   default="auto", help="Mode de mise à jour")
    p.add_argument("--usb-path", help="Chemin de la clé USB (auto-détecté si omis)")
    p.add_argument("--version", help="Version cible pour rollback")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_update)

    # train-scheduler
    p = sub.add_parser("train-scheduler", help="Planificateur d'entrainement automatique")
    p.add_argument("action", choices=["check", "run", "schedule", "stats"])
    p.add_argument("--force", action="store_true", help="Forcer l'entrainement")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_train_scheduler)

    # vpn (Tailscale-like)
    p = sub.add_parser("vpn", help="VPN WireGuard PixelOS (comme Tailscale)")
    p.add_argument("action", choices=["status", "start", "stop", "restart",
                                      "start-all", "stop-all",
                                      "up", "down", "ip", "ips",
                                      "install", "uninstall",
                                      "client", "clients", "forwarder",
                                      "autostart"])
    p.add_argument("sub", nargs="?", help="Sous-action (forwarder: start|stop|status, autostart: enable|disable)")
    p.add_argument("--name", help="Nom du client")
    p.add_argument("--endpoint", default="196.179.160.78:51820", help="Endpoint serveur")
    p.add_argument("--full", action="store_true", help="Status détaillé")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_vpn)

    # federation (réseau mondial PixelOS)
    p = sub.add_parser("federation", help="Réseau fédéré mondial PixelOS")
    p.add_argument("action", choices=["status", "announce", "peers",
                                       "species", "species-create", "discover",
                                       "mesh-status", "mesh-connect",
                                       "gov-status", "gov-register",
                                       "gov-propose", "gov-vote"])
    p.add_argument("query", nargs="?", help="Recherche espèce / titre proposition")
    p.add_argument("--description", help="Description proposition")
    p.add_argument("--type", help="Type proposition (update, policy, new_member)")
    p.add_argument("--proposal-id", help="ID de la proposition")
    p.add_argument("--vote", type=bool, default=True, help="Vote pour (True) ou contre (False)")
    p.add_argument("--name", help="Nom membre / nom commun")
    p.add_argument("--scientific-name", help="Nom scientifique")
    p.add_argument("--common-name", help="Nom commun")
    p.add_argument("--family", help="Famille")
    p.add_argument("--genus", help="Genre")
    p.add_argument("--latitude", type=float, default=0.0, help="Latitude")
    p.add_argument("--longitude", type=float, default=0.0, help="Longitude")
    p.add_argument("--region", help="Région d'origine")
    p.add_argument("--country", help="Pays")
    p.add_argument("--biome", help="Biome")
    p.add_argument("--race-type", choices=["rare","locale","ancienne","commerciale","sauvage"],
                   default="locale")
    p.add_argument("--conservation-status", choices=["eteinte","gravement_menacee","menacee",
                   "vulnerable","quasi_menacee","preoccupation_mineure",
                   "donnees_insuffisantes","non_evaluee"], default="non_evaluee")
    p.add_argument("--conservation-source", default="association")
    p.add_argument("--confidentiality", choices=["public","membres","association","prive"],
                   default="public")
    p.add_argument("--water-need", choices=["faible","moyen","eleve"], default="moyen")
    p.add_argument("--status", help="Filtrer par statut conservation")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_federation)

    # ftp (zones agricoles)
    p = sub.add_parser("ftp", help="Gestion FTP zones agricoles (OpenBSD)")
    p.add_argument("action", choices=["zones", "create", "delete"])
    p.add_argument("--zone", help="Nom de la zone")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_ftp)

    # dns
    p = sub.add_parser("dns", help="Serveur DNS privé PixelOS")
    p.add_argument("action", choices=["start", "stop", "restart", "status", "records"])
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_dns)

    p = sub.add_parser("production", help="Gestion production: préparation sol, plantation arbres, plans")
    p.add_argument("action", choices=["dashboard", "stats",
                                       "soil-list", "soil-create", "soil-show", "soil-update", "soil-amend",
                                       "planting-list", "planting-create", "planting-show", "planting-update",
                                       "plan-list", "plan-create", "plan-show", "plan-update"])
    p.add_argument("soil_prep_id", nargs="?", help="ID préparation sol")
    p.add_argument("planting_id", nargs="?", help="ID plantation")
    p.add_argument("plan_id", nargs="?", help="ID plan de production")
    p.add_argument("--name", help="Nom")
    p.add_argument("--space", help="ID espace/zone")
    p.add_argument("--sub-zone", help="ID sous-zone")
    p.add_argument("--product-id", help="ID produit lifecycle")
    p.add_argument("--product-name", help="Nom du produit")
    p.add_argument("--variety", help="Variété")
    p.add_argument("--rootstock", help="Porte-greffe")
    p.add_argument("--preparation-type", choices=["labour", "decompaction", "buttage", "planche",
                   "billonnage", "pseudo-labour", "travail_minimal", "strip_till", "semi_direct"],
                   default="labour", help="Type de préparation sol")
    p.add_argument("--area-m2", type=float, help="Surface (m²)")
    p.add_argument("--depth-cm", type=float, help="Profondeur travail (cm)")
    p.add_argument("--soil-condition", help="État du sol")
    p.add_argument("--texture", help="Texture du sol")
    p.add_argument("--plant-count", type=int, default=0, help="Nombre de plants")
    p.add_argument("--spacing-m", type=float, help="Espacement interligne (m)")
    p.add_argument("--spacing-plant", type=float, help="Espacement sur ligne (m)")
    p.add_argument("--planting-method", choices=["trou", "butte", "tranchée", "conteneur",
                   "motte", "racine_nue"], default="trou", help="Méthode de plantation")
    p.add_argument("--stake-type", choices=["tuteur_bois", "tuteur_metal", "haubanage", "aucun"],
                   default="aucun", help="Type tuteur")
    p.add_argument("--initial-watering-l", type=float, default=0, help="Arrosage initial L/plant")
    p.add_argument("--mulch-type", choices=["paille", "BRF", "toile_geotextile", "plastique_noir",
                   "copeaux", "écorce", "feuilles", "aucun"], default="aucun", help="Type paillage")
    p.add_argument("--irrigation-type", choices=["goutte_a_goutte", "micro-aspersion", "aspersion",
                   "gravitaire", "aucun"], default="aucun", help="Type irrigation")
    p.add_argument("--hole-depth-cm", type=float, default=0, help="Profondeur trou (cm)")
    p.add_argument("--hole-width-cm", type=float, default=0, help="Largeur trou (cm)")
    p.add_argument("--amendment-type", choices=["compost", "fumier", "engrais_vert", "NPK",
                   "organique", "chaux", "soufre", "gypse", "biochar", "cendre", "guano"],
                   help="Type amendement")
    p.add_argument("--quantity-kg", type=float, help="Quantité (kg)")
    p.add_argument("--season", help="Saison (printemps, été, automne, hiver)")
    p.add_argument("--year", type=int, help="Année")
    p.add_argument("--estimated-yield-kg", type=float, help="Rendement estimé (kg)")
    p.add_argument("--start-date", help="Date début (YYYY-MM-DD)")
    p.add_argument("--estimated-end-date", help="Date fin estimée (YYYY-MM-DD)")
    p.add_argument("--status", choices=["planned", "in_progress", "completed", "cancelled",
                                        "draft", "active"],
                   help="Statut")
    p.add_argument("--notes", help="Notes")
    p.add_argument("--assigned-to", help="Assigné à")
    p.add_argument("--json", action="store_true", help="Sortie JSON brute")
    p.set_defaults(func=cmd_production)

    # ipfs (stockage décentralisé)
    p = sub.add_parser("ipfs", help="Stockage décentralisé IPFS")
    p.add_argument("action", choices=["status", "init", "start", "stop",
                                       "publish", "fetch", "sync"])
    p.add_argument("cid", nargs="?", help="CID IPFS ou IPNS")
    p.add_argument("--json", action="store_true", help="Sortie JSON")
    p.set_defaults(func=cmd_ipfs)

    # matrix (messagerie communauté)
    p = sub.add_parser("matrix", help="Messagerie communauté Matrix")
    p.add_argument("action", choices=["status", "configure", "test"])
    p.add_argument("--homeserver", help="Serveur Matrix")
    p.add_argument("--user", help="User ID Matrix")
    p.add_argument("--token", help="Access token")
    p.add_argument("--room", help="Room ID")
    p.add_argument("--json", action="store_true", help="Sortie JSON")
    p.set_defaults(func=cmd_matrix)

    # portal (bootstrap communauté)
    p = sub.add_parser("portal", help="Portail communauté PixelOS")
    p.add_argument("action", choices=["status", "register-seed", "join",
                                       "mirror-add", "iso-url"])
    p.add_argument("--name", help="Nom du miroir")
    p.add_argument("--url", help="URL du miroir")
    p.add_argument("--country", help="Pays")
    p.add_argument("--nickname", help="Surnom")
    p.add_argument("--email", help="Email")
    p.add_argument("--reason", help="Raison de rejoindre")
    p.add_argument("--json", action="store_true", help="Sortie JSON")
    p.set_defaults(func=cmd_portal)

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
