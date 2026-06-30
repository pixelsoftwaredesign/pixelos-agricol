#!/usr/bin/env python3
"""
PixIPC — Bus de messages interne et interface standardisée des modules PixelOS.

Fournit:
  - MessageBus : bus IPC central (sockets TCP locaux, pub/sub, request/response)
  - PixModule  : classe de base que tous les modules PixelOS doivent étendre
  - Heartbeat  : mécanisme standard d'annonce de vie des modules

Architecture:
  Chaque module s'enregistre auprès du bus, envoie son heartbeat périodiquement,
  et écoute les commandes qui lui sont destinées. PixStat centralise les
  heartbeats et alerte PixOrchestrator en cas de défaillance.
"""

import os
import json
import time
import socket
import threading
import hashlib
from datetime import datetime, timezone
from typing import Optional, Callable
from pathlib import Path

# ── Constantes ──────────────────────────────────────────

IPC_HOST = "127.0.0.1"
IPC_PORT = 9101
IPC_BUF = 65536
HB_EXPECTED_INTERVAL = 5.0
HB_MISSED_LIMIT = 3

MSG_TYPE_HEARTBEAT = "heartbeat"
MSG_TYPE_COMMAND = "command"
MSG_TYPE_REQUEST = "request"
MSG_TYPE_RESPONSE = "response"
MSG_TYPE_EVENT = "event"
MSG_TYPE_REGISTER = "register"
MSG_TYPE_ALERT = "alert"

PRIORITY_LOW = 0
PRIORITY_NORMAL = 1
PRIORITY_HIGH = 2
PRIORITY_CRITICAL = 3

MODULE_STATUSES = {
    "INIT": "initialisation",
    "RUNNING": "en fonctionnement",
    "DEGRADED": "dégradé",
    "ERROR": "erreur",
    "STOPPED": "arrêté",
    "UNKNOWN": "inconnu",
}

IPC_DIR = "/var/run/pixelos/ipc"


# ── Message ─────────────────────────────────────────────

class Message:
    """Message normalisé échangé sur le bus IPC."""

    def __init__(self, msg_type: str, source: str, target: str = "",
                 payload: dict = None, msg_id: str = "",
                 priority: int = PRIORITY_NORMAL):
        self.msg_id = msg_id or hashlib.sha256(
            f"{source}{time.time()}{os.urandom(4).hex()}".encode()
        ).hexdigest()[:16]
        self.type = msg_type
        self.source = source
        self.target = target
        self.payload = payload or {}
        self.priority = max(PRIORITY_LOW, min(PRIORITY_CRITICAL, priority))
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "payload": self.payload,
            "priority": self.priority,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> "Message":
        return Message(
            msg_type=data.get("type", ""),
            source=data.get("source", ""),
            target=data.get("target", ""),
            payload=data.get("payload", {}),
            msg_id=data.get("msg_id", ""),
            priority=data.get("priority", PRIORITY_NORMAL),
        )

    def serialize(self) -> bytes:
        return json.dumps(self.to_dict()).encode()

    @staticmethod
    def deserialize(data: bytes) -> "Message":
        return Message.from_dict(json.loads(data.decode()))

    def reply(self, payload: dict = None) -> "Message":
        return Message(
            msg_type=MSG_TYPE_RESPONSE,
            source=self.target or "bus",
            target=self.source,
            payload=payload,
            priority=self.priority,
        )


# ── MessageBus ──────────────────────────────────────────

class MessageBus:
    """Bus IPC central. Singleton accessible globalement.

    Maintient:
      - Modules enregistrés (nom -> infos)
      - File d'attente des messages
      - Connexions socket pour chaque module
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.modules: dict[str, dict] = {}
        self._subscribers: dict[str, list[str]] = {}
        self._pending: list[Message] = []
        self._lock = threading.Lock()
        self._server: Optional[socket.socket] = None
        self._stop = threading.Event()
        self._module_connections: dict[str, socket.socket] = {}
        self._callbacks: dict[str, list[Callable]] = {}
        self._ensure_ipc_dir()

    def _ensure_ipc_dir(self):
        Path(IPC_DIR).mkdir(parents=True, exist_ok=True)

    # ── Demarrage du bus ─────────────────────────────────

    def start(self):
        """Démarre le serveur IPC sur le port configuré."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((IPC_HOST, IPC_PORT))
            self._server.listen(10)
            self._server.settimeout(1.0)
        except OSError as e:
            self._server = None
            return

        def accept_loop():
            while not self._stop.is_set():
                try:
                    conn, addr = self._server.accept()
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
                except socket.timeout:
                    continue
                except Exception:
                    break

        threading.Thread(target=accept_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        for mod, conn in self._module_connections.items():
            try:
                conn.close()
            except Exception:
                pass

    def _handle_client(self, conn: socket.socket, addr):
        buf = b""
        while not self._stop.is_set():
            try:
                data = conn.recv(IPC_BUF)
                if not data:
                    break
                buf += data
                # Traiter les messages complets (séparateur newline)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = Message.deserialize(line)
                        self._process_message(msg, conn)
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                break
        conn.close()

    def _process_message(self, msg: Message, conn: socket.socket):
        if msg.type == MSG_TYPE_REGISTER:
            self.modules[msg.source] = {
                "status": "RUNNING",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "info": msg.payload,
            }
            self._module_connections[msg.source] = conn

        elif msg.type == MSG_TYPE_HEARTBEAT:
            if msg.source in self.modules:
                self.modules[msg.source]["last_heartbeat"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                self.modules[msg.source]["status"] = msg.payload.get("status", "RUNNING")

        elif msg.type == MSG_TYPE_REQUEST:
            self._insert_pending(msg)
            self._trigger_callbacks("request", msg)

        elif msg.type == MSG_TYPE_COMMAND:
            self._insert_pending(msg)
            self._trigger_callbacks("command", msg)

        elif msg.type == MSG_TYPE_EVENT:
            self._trigger_callbacks("event", msg)

        # Forward si target specifié
        if msg.target and msg.target in self._module_connections:
            try:
                self._module_connections[msg.target].sendall(
                    msg.serialize() + b"\n"
                )
            except Exception:
                pass

    def _trigger_callbacks(self, event: str, msg: Message):
        for cb in self._callbacks.get(event, []):
            try:
                cb(msg)
            except Exception:
                pass

    # ── API pour les modules ─────────────────────────────

    def _insert_pending(self, msg: Message):
        """Insère dans _pending par ordre de priorité (desc)."""
        i = 0
        while i < len(self._pending) and self._pending[i].priority >= msg.priority:
            i += 1
        self._pending.insert(i, msg)

    def publish(self, msg: Message):
        """Publie un message sur le bus."""
        self._insert_pending(msg)
        self._trigger_callbacks(msg.type, msg)

    def subscribe(self, event: str, callback: Callable):
        """Souscrit à un type d'événement."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def send_command(self, target: str, command: str, params: dict = None,
                     priority: int = PRIORITY_NORMAL) -> bool:
        """Envoie une commande à un module spécifique avec niveau de priorité."""
        if target not in self._module_connections:
            return False
        msg = Message(MSG_TYPE_COMMAND, "bus", target, {
            "command": command,
            "params": params or {},
        }, priority=priority)
        try:
            self._module_connections[target].sendall(msg.serialize() + b"\n")
            return True
        except Exception:
            return False

    # ── État ─────────────────────────────────────────────

    def get_modules(self) -> dict:
        return dict(self.modules)

    def get_module(self, name: str) -> Optional[dict]:
        return self.modules.get(name)

    def stats(self) -> dict:
        now = time.time()
        alive = 0
        dead = 0
        for name, info in self.modules.items():
            hb = info.get("last_heartbeat", "")
            if hb:
                try:
                    delta = now - datetime.fromisoformat(hb).timestamp()
                    if delta < HB_EXPECTED_INTERVAL * HB_MISSED_LIMIT:
                        alive += 1
                    else:
                        dead += 1
                except Exception:
                    dead += 1
        return {
            "modules_registered": len(self.modules),
            "modules_alive": alive,
            "modules_dead": dead,
            "pending_messages": len(self._pending),
            "subscribers": len(self._callbacks),
            "server_running": self._server is not None,
            "host": IPC_HOST,
            "port": IPC_PORT,
        }


# ── PixModule (classe de base) ──────────────────────────

class PixModule:
    """Classe de base pour tous les modules PixelOS.

    Chaque module doit:
      - Appeler __init__ avec son nom
      - Implémenter handle_request()
      - Lancer send_heartbeat_loop() dans un thread
      - Appeler register() au démarrage
    """

    def __init__(self, name: str, version: str = "1.0"):
        self.name = name
        self.version = version
        self.status = "INIT"
        self.bus = MessageBus()
        self.error_count = 0
        self._hb_stop = threading.Event()
        self._registered = False

    def register(self, info: dict = None):
        """Enregistre le module auprès du bus IPC."""
        info = info or {}
        info["version"] = self.version
        info["pid"] = os.getpid()
        msg = Message(MSG_TYPE_REGISTER, self.name, "bus", info)
        self.bus.publish(msg)
        self._registered = True
        self.status = "RUNNING"

    def send_heartbeat(self):
        """Envoie une impulsion de vie au bus."""
        msg = Message(MSG_TYPE_HEARTBEAT, self.name, "bus", {
            "status": self.status,
            "error_count": self.error_count,
            "pid": os.getpid(),
        })
        self.bus.publish(msg)

    def send_heartbeat_loop(self, interval: float = HB_EXPECTED_INTERVAL):
        """Boucle d'envoi périodique du heartbeat."""

        def loop():
            while not self._hb_stop.is_set():
                self.send_heartbeat()
                self._hb_stop.wait(interval)

        threading.Thread(target=loop, daemon=True).start()

    def handle_request(self, msg: Message) -> dict:
        """Traite une requête/commande. À surcharger dans les sous-classes."""
        return {"status": "unhandled", "module": self.name}

    def start_command_listener(self):
        """Écoute les commandes entrantes sur le bus."""
        def handler(msg: Message):
            if msg.target and msg.target != self.name:
                return
            if msg.type in (MSG_TYPE_COMMAND, MSG_TYPE_REQUEST):
                result = self.handle_request(msg)
                if msg.source and msg.source != "bus":
                    reply = msg.reply(result)
                    self.bus.publish(reply)

        self.bus.subscribe("command", handler)
        self.bus.subscribe("request", handler)

    def set_status(self, status: str):
        self.status = status if status in MODULE_STATUSES else "UNKNOWN"

    def stop_heartbeat(self):
        self._hb_stop.set()

    def __repr__(self):
        return f"<PixModule:{self.name} status={self.status}>"
