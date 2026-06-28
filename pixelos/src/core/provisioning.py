"""Provisioning automatique des capteurs découverts dans les zones."""

import os
import yaml
import json
import structlog
from pathlib import Path
from datetime import datetime
from typing import Optional

from core.config import PixelOSConfig
from core.mqtt import PixelOSMQTT


log = structlog.get_logger()


class ZoneManager:
    """Gestion des zones et auto-enregistrement des capteurs."""

    TYPE_MAP = {
        "sol":    {"type": "capteur_sol",    "icon": "🌱", "default_poll": 10},
        "vanne":  {"type": "vanne",          "icon": "💧", "default_poll": 5},
        "meteo":  {"type": "meteo",          "icon": "🌤️", "default_poll": 30},
        "debit":  {"type": "debitmetre",     "icon": "📊", "default_poll": 5},
        "pir":    {"type": "pir",            "icon": "🚨", "default_poll": 2},
        "pompe":  {"type": "pompe",          "icon": "⚡", "default_poll": 5},
    }

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            PixelOSConfig.CONFIG_PATHS.insert(0, config_path)
        self.config = PixelOSConfig()
        self.nodes_path = self._find_nodes_path()
        self.mqtt = PixelOSMQTT()

    def _find_nodes_path(self) -> str:
        base = Path(self.config.path).parent if self.config.path else Path("./config")
        for p in [base / "nodes.yaml", Path("./config/nodes.yaml")]:
            if p.exists():
                return str(p)
        return "./config/nodes.yaml"

    def list_zones(self) -> list[dict]:
        """Liste toutes les zones (groupes de nœuds par location)."""
        zones = {}
        for n in self.config.nodes.values():
            loc = n.get("location", "Non assigné")
            if loc not in zones:
                zones[loc] = {
                    "location": loc,
                    "count": 0,
                    "nodes": [],
                }
            type_info = self.TYPE_MAP.get(n["type"], {"icon": "📡"})
            zones[loc]["count"] += 1
            zones[loc]["nodes"].append({
                "id": n["id"],
                "type": n["type"],
                "icon": type_info["icon"],
                "addr": n["addr"],
                "com": n.get("communication", "?"),
            })
        return list(zones.values())

    def detect_new(self, discovered: list[dict]) -> list[dict]:
        """Compare la liste des découverts avec les nœuds existants."""
        existing = set(self.config.nodes.keys())
        new_nodes = []

        for d in discovered:
            node_id = d.get("nom") or f"{d['type']}_{d.get('addr', d.get('mac', 'unknown'))}"
            if node_id in existing:
                continue

            type_info = self.TYPE_MAP.get(d["type"], {"type": d["type"], "icon": "📡"})
            entry = {
                "id": node_id,
                "addr": d.get("addr", 0),
                "type": type_info["type"],
                "location": d.get("location", "Nouveau (auto-détecté)"),
                "communication": d.get("communication", d.get("source", "wifi")),
                "protocol": d.get("protocol", "auto"),
                "source": d.get("source", "scan"),
                "mac": d.get("mac", ""),
                "rssi": d.get("rssi", 0),
                "detected_at": datetime.now().isoformat(),
            }

            # Ajouter les capteurs par défaut selon le type
            sensor_defaults = {
                "capteur_sol": {
                    "humidity": {"reg": 0, "factor": 0.1, "unit": "%"},
                    "temperature": {"reg": 1, "factor": 0.1, "unit": "°C"},
                },
                "vanne": {"valve": {"reg": 0, "unit": "ON/OFF"}},
                "meteo": {
                    "temperature": {"unit": "°C"},
                    "humidity": {"unit": "%"},
                    "pression": {"unit": "hPa"},
                },
                "debitmetre": {
                    "flow": {"reg": 0, "unit": "L/min"},
                    "total": {"reg": 1, "unit": "L"},
                },
                "pir": {"motion": {"reg": 0, "unit": "detect"}},
            }
            if type_info["type"] in sensor_defaults:
                entry["sensors"] = sensor_defaults[type_info["type"]]

            new_nodes.append(entry)

        return new_nodes

    def register(self, node_def: dict, zone_location: Optional[str] = None) -> bool:
        """Enregistre un nœud découvert dans la configuration."""
        if zone_location:
            node_def["location"] = zone_location

        node_id = node_def["id"]
        if node_id in self.config.nodes:
            log.warning("Nœud déjà enregistré", node=node_id)
            return False

        # Ajouter aux nodes
        self.config.nodes[node_id] = node_def

        # Sauvegarder dans nodes.yaml
        self._save_nodes()

        # Notifier via MQTT
        try:
            self.mqtt.connect()
            self.mqtt.publish(f"pixelos/node/{node_id}/registered", {
                "node": node_def,
                "ts": datetime.now().isoformat(),
            })
            self.mqtt.disconnect()
        except Exception as e:
            log.warning("Échec notification MQTT", error=str(e))

        log.info("Nœud enregistré", node=node_id, zone=zone_location)
        return True

    def register_batch(self, nodes: list[dict], zone: str = "Auto-détecté") -> dict:
        """Enregistre plusieurs nœuds d'un coup."""
        results = {"registered": [], "skipped": [], "errors": []}
        for n in nodes:
            try:
                if self.register(n, zone):
                    results["registered"].append(n["id"])
                else:
                    results["skipped"].append(n["id"])
            except Exception as e:
                results["errors"].append({"node": n["id"], "error": str(e)})
        return results

    def _save_nodes(self) -> None:
        """Sauvegarde dans nodes.yaml."""
        data = {"nodes": list(self.config.nodes.values())}
        with open(self.nodes_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        log.info("nodes.yaml mis à jour", path=self.nodes_path)

    def assign_to_zone(self, node_id: str, location: str) -> bool:
        """Assigne un nœud existant à une nouvelle zone."""
        if node_id not in self.config.nodes:
            log.error("Nœud introuvable", node=node_id)
            return False
        self.config.nodes[node_id]["location"] = location
        self._save_nodes()
        log.info("Nœud assigné à la zone", node=node_id, zone=location)
        return True

    def remove(self, node_id: str) -> bool:
        """Retire un nœud du système."""
        if node_id not in self.config.nodes:
            return False
        del self.config.nodes[node_id]
        self._save_nodes()
        log.info("Nœud retiré", node=node_id)
        return True
