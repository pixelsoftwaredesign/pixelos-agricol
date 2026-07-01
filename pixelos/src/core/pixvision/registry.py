"""
PixVision — Référentiel des Objets (ObjectRegistry).

Fusion des détections :
  - Physique (caméra → YOLO → DetectionResult)
  - Réseau (WiFi → ARP → NetworkDevice)

Stockage SQLite avec messages PixIPC vers le Digital Twin.
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.pixipc import bus as pixipc
from .detector import detector, env_map
from .scanner import scanner
from .oui_db import lookup_oui

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pixvision"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "registry.db"

# Map YOLO class name → device type
PHYSICAL_TO_TYPE = {
    "HUMAIN": ("humain", False),
    "ANIMAL": ("animal", False),
    "ARBRE": ("arbre", True),
    "ROCHER": ("rocher", True),
    "BATIMENT": ("batiment", True),
    "CLOTURE": ("cloture", True),
    "OBSTACLE_INCONNU": ("obstacle_inconnu", False),
}

# Map network device type → IoT class
NETWORK_TO_IOT = {
    "station_meteo": "STATION_METEO",
    "capteur_sol": "CAPTEUR_SOL",
    "irrigation": "IRRIGATION",
    "drone": "DRONE",
    "gnss": "GNSS",
    "automate": "AUTOMATE",
    "solaire": "SOLAIRE",
    "iot_gateway": "GATEWAY",
    "iot_broker": "BROKER_MQTT",
}


class ObjectRegistry:
    """Registre fusionné des objets détectés.

    Utilise SQLite pour la persistance.
    Chaque entrée lie :
      - ID physique (classe YOLO + position)
      - ID réseau (MAC + IP + fabricant OUI)
      - Position GPS / coordonnées carte
      - Statut connecté (RSSI, online/offline)
    """

    def __init__(self, db_path: str = None):
        self._path = Path(db_path) if db_path else DB_PATH
        self._lock = threading.Lock()
        self._init_db()
        # S'abonner aux messages PixIPC entrants
        pixipc.subscribe("DETECTION", self._on_pixipc_msg)

    def _init_db(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS objects (
                    obj_id TEXT PRIMARY KEY,
                    physical_class TEXT DEFAULT '',
                    physical_confidence REAL DEFAULT 0.0,
                    network_mac TEXT DEFAULT '',
                    network_ip TEXT DEFAULT '',
                    network_manufacturer TEXT DEFAULT '',
                    device_type TEXT DEFAULT 'inconnu',
                    confidence REAL DEFAULT 0.0,
                    pos_x REAL DEFAULT 0.0,
                    pos_y REAL DEFAULT 0.0,
                    rssi INTEGER DEFAULT -100,
                    status TEXT DEFAULT 'unknown',
                    source TEXT DEFAULT 'unknown',
                    first_seen TEXT DEFAULT '',
                    last_seen TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_type
                ON objects(device_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_status
                ON objects(status)
            """)
            conn.commit()

    def _connect(self):
        return sqlite3.connect(str(self._path), timeout=10)

    # ── Fusion physique ─────────────────────────────────────

    def register_physical(self, class_name: str, confidence: float,
                          pos_x: float, pos_y: float) -> dict:
        """Enregistrer une détection physique (caméra → YOLO)."""
        dtype, _ = PHYSICAL_TO_TYPE.get(class_name, ("inconnu", False))
        obj_id = f"{dtype}_{pos_x:.1f}_{pos_y:.1f}"

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM objects WHERE obj_id = ?", (obj_id,)
                ).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE objects SET
                            physical_confidence = MAX(physical_confidence, ?),
                            confidence = MAX(confidence, ?),
                            last_seen = ?,
                            status = ?
                        WHERE obj_id = ?
                    """, (confidence, confidence * 0.6, now, "online", obj_id))
                else:
                    conn.execute("""
                        INSERT INTO objects
                            (obj_id, physical_class, physical_confidence,
                             device_type, confidence, pos_x, pos_y,
                             status, source, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (obj_id, class_name, confidence,
                          dtype, confidence * 0.6, pos_x, pos_y,
                          "online", "physical", now, now))

                conn.commit()
                obj = self._get_by_id(conn, obj_id)

        # Mettre à jour EnvironmentMap si obstacle statique
        if dtype in ("arbre", "rocher", "batiment", "cloture", "obstacle_inconnu"):
            env_map.update(class_name, pos_x, pos_y, confidence)

        # Publier message PixIPC
        pixipc.publish("DETECTION", {
            "obj_id": obj_id,
            "type": dtype,
            "pos": {"x": pos_x, "y": pos_y},
            "source": "physical",
            "confidence": confidence,
            "status": "ONLINE",
        })

        # Créer un jumeau numérique si pas déjà fait
        self._ensure_twin(obj)

        return obj

    def register_network(self, mac: str, ip: str = "",
                         manufacturer: str = "",
                         device_type: str = "inconnu",
                         rssi: int = -100) -> dict:
        """Enregistrer une détection réseau (WiFi → ARP)."""
        oui_info = lookup_oui(mac) if not manufacturer else {
            "manufacturer": manufacturer,
            "device_type": device_type,
            "confidence": 0.8,
        }
        mfr = manufacturer or oui_info["manufacturer"]
        dtype = device_type if device_type != "inconnu" else oui_info["device_type"]
        conf = oui_info["confidence"] if not manufacturer else 0.8

        now = datetime.now(timezone.utc).isoformat()
        obj_id = f"net_{mac.replace(':', '')}"

        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM objects WHERE network_mac = ?", (mac,)
                ).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE objects SET
                            network_ip = ?,
                            network_manufacturer = ?,
                            device_type = CASE WHEN ? != 'inconnu' THEN ? ELSE device_type END,
                            confidence = MAX(confidence, ?),
                            rssi = ?,
                            last_seen = ?,
                            status = ?
                        WHERE obj_id = ?
                    """, (ip, mfr, dtype, dtype, conf, rssi, now, "online", existing[0]))

                    obj = self._get_by_id(conn, existing[0])
                else:
                    # Fusion : cherche un objet physique compatible
                    iot_class = NETWORK_TO_IOT.get(dtype, "")
                    physical_match = None
                    if iot_class:
                        physical_match = conn.execute(
                            "SELECT * FROM objects WHERE device_type = ? AND source = 'physical'",
                            (iot_class.lower(),)
                        ).fetchone()

                    if physical_match:
                        # Fusionner : physique existant + réseau
                        conn.execute("""
                            UPDATE objects SET
                                network_mac = ?,
                                network_ip = ?,
                                network_manufacturer = ?,
                                confidence = MIN(1.0, physical_confidence + ?),
                                rssi = ?,
                                last_seen = ?,
                                status = ?,
                                source = 'fused'
                            WHERE obj_id = ?
                        """, (mac, ip, mfr, conf, rssi, now, "online",
                              physical_match[0]))
                        obj = self._get_by_id(conn, physical_match[0])
                    else:
                        conn.execute("""
                            INSERT INTO objects
                                (obj_id, network_mac, network_ip,
                                 network_manufacturer, device_type,
                                 confidence, rssi, status, source,
                                 first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (obj_id, mac, ip, mfr, dtype,
                              conf, rssi, "online", "network", now, now))
                        obj = self._get_by_id(conn, obj_id)

                conn.commit()

        pixipc.publish("DETECTION", {
            "obj_id": obj["obj_id"],
            "type": obj["device_type"],
            "pos": {"x": obj["pos_x"], "y": obj["pos_y"]},
            "rssi": rssi,
            "mac": mac,
            "manufacturer": mfr,
            "source": "network",
            "confidence": obj["confidence"],
            "status": "ONLINE",
        })

        self._ensure_twin(obj)
        return obj

    def _get_by_id(self, conn, obj_id: str) -> dict:
        row = conn.execute(
            "SELECT * FROM objects WHERE obj_id = ?", (obj_id,)
        ).fetchone()
        if not row:
            return {}
        return {
            "obj_id": row[0],
            "physical_class": row[1],
            "physical_confidence": row[2],
            "network_mac": row[3],
            "network_ip": row[4],
            "network_manufacturer": row[5],
            "device_type": row[6],
            "confidence": row[7],
            "pos_x": row[8],
            "pos_y": row[9],
            "rssi": row[10],
            "status": row[11],
            "source": row[12],
            "first_seen": row[13],
            "last_seen": row[14],
        }

    def _ensure_twin(self, obj: dict):
        """Créer/synchroniser un jumeau numérique dans le Digital Twin."""
        try:
            from core.digital_twin.twin import DigitalTwin
            dt = DigitalTwin()

            obj_id = obj.get("obj_id", "")
            dtype = obj.get("device_type", "inconnu")
            conf = obj.get("confidence", 0.0)
            pos_x = obj.get("pos_x", 0.0)
            pos_y = obj.get("pos_y", 0.0)

            # Vérifier si le twin existe
            existing = dt.get(obj_id)
            if existing:
                dt.sync_sensor(obj_id, "confidence", conf, unit="%")
                dt.sync_sensor(obj_id, "pos_x", pos_x, unit="m")
                dt.sync_sensor(obj_id, "pos_y", pos_y, unit="m")
                dt.sync_state(obj_id, {
                    "status": obj.get("status", "unknown"),
                    "last_seen": obj.get("last_seen", ""),
                })
            else:
                dt.create(obj_id, entity_type=dtype, metadata={
                    "source": obj.get("source", "unknown"),
                    "confidence": conf,
                    "position": {"x": pos_x, "y": pos_y},
                    "rssi": obj.get("rssi", -100),
                    "mac": obj.get("network_mac", ""),
                    "manufacturer": obj.get("network_manufacturer", ""),
                })
        except Exception as e:
            print(f"[Registry] Erreur twin {obj.get('obj_id', '')}: {e}")

    # ── API publique ────────────────────────────────────────

    def list_objects(self, device_type: str = None,
                     status: str = None) -> list[dict]:
        with self._connect() as conn:
            query = "SELECT * FROM objects"
            params = []
            conditions = []
            if device_type:
                conditions.append("device_type = ?")
                params.append(device_type)
            if status:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY last_seen DESC"
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_dict(r) for r in rows]

    def get_object(self, obj_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM objects WHERE obj_id = ?", (obj_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row) -> dict:
        return {
            "obj_id": row[0],
            "physical_class": row[1],
            "physical_confidence": row[2],
            "network_mac": row[3],
            "network_ip": row[4],
            "network_manufacturer": row[5],
            "device_type": row[6],
            "confidence": row[7],
            "pos_x": row[8],
            "pos_y": row[9],
            "rssi": row[10],
            "status": row[11],
            "source": row[12],
            "first_seen": row[13],
            "last_seen": row[14],
        }

    def set_status(self, obj_id: str, status: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE objects SET status = ?, last_seen = ? WHERE obj_id = ?",
                    (status, now, obj_id)
                )
                conn.commit()
                obj = self._get_by_id(conn, obj_id)
        return obj

    def delete_object(self, obj_id: str) -> dict:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM objects WHERE obj_id = ?", (obj_id,))
                conn.commit()
        return {"deleted": obj_id}

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            by_type = conn.execute(
                "SELECT device_type, COUNT(*) FROM objects GROUP BY device_type"
            ).fetchall()
            by_source = conn.execute(
                "SELECT source, COUNT(*) FROM objects GROUP BY source"
            ).fetchall()
            by_status = conn.execute(
                "SELECT status, COUNT(*) FROM objects GROUP BY status"
            ).fetchall()
        return {
            "total": total,
            "by_type": dict(by_type),
            "by_source": dict(by_source),
            "by_status": dict(by_status),
        }

    def _on_pixipc_msg(self, msg: dict):
        """Callback pour les messages PixIPC entrants."""
        pass  # Les messages sont déjà traités par register_physical/network

    def auto_fuse(self):
        """Parcourt les objets physiques sans MAC et tente de les fusionner
        avec des objets réseau."""
        with self._connect() as conn:
            orphans = conn.execute(
                "SELECT * FROM objects WHERE source = 'physical' AND network_mac = ''"
            ).fetchall()

            network_devices = conn.execute(
                "SELECT * FROM objects WHERE source = 'network'"
            ).fetchall()

        fused = 0
        for phys in orphans:
            ptype = phys[6]  # device_type
            for net in network_devices:
                ntype = net[6]
                # Fusion si même type et positions proches
                if ptype == ntype:
                    ppos_x, ppos_y = phys[8], phys[9]
                    npos_x, npos_y = net[8], net[9]
                    # Si pas de position réseau, fusionner quand même
                    if npos_x == 0 and npos_y == 0:
                        with self._lock:
                            with self._connect() as conn:
                                conn.execute("""
                                    UPDATE objects SET
                                        network_mac = ?,
                                        network_ip = ?,
                                        network_manufacturer = ?,
                                        confidence = MIN(1.0, ? + ?),
                                        source = 'fused'
                                    WHERE obj_id = ?
                                """, (net[3], net[4], net[5],
                                      phys[2], net[7], phys[0]))
                                conn.commit()
                                conn.execute(
                                    "DELETE FROM objects WHERE obj_id = ?",
                                    (net[0],)
                                )
                                conn.commit()
                        fused += 1
                        break
        return fused


# ── Singleton ───────────────────────────────────────────────

registry = ObjectRegistry()

__all__ = ["ObjectRegistry", "registry"]
