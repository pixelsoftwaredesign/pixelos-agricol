"""
PixIPC — Message bus Pixel OS.

Bus de messages asynchrone pour la communication inter-modules :
  - PixVision → Digital Twin (détections)
  - PixDetector → PixNav (arrêt d'urgence)
  - Scanner IoT → ObjectRegistry (périphériques)

Architecture publish/subscribe en mémoire avec file JSONL persistante.
"""

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "pixipc"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = DATA_DIR / "messages.jsonl"


class PixIPC:
    """Bus de messages interne.

    Usage:
        ipc = PixIPC()
        ipc.subscribe("DETECTION", my_handler)
        ipc.publish("DETECTION", {"obj_id": "...", "pos": {...}})
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._message_count = 0
        self._message_log: list[dict] = []

    def publish(self, msg_type: str, payload: dict) -> dict:
        """Publier un message sur le bus.

        Returns:
            dict with message id, type, timestamp.
        """
        msg = {
            "id": self._message_count + 1,
            "type": msg_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._message_count += 1

        with self._lock:
            # Log en mémoire
            self._message_log.append(msg)

            # Persistance JSONL
            try:
                with open(LOG_FILE, "a") as f:
                    f.write(json.dumps(msg) + "\n")
            except Exception:
                pass

            # Notifier les abonnés
            for cb in self._subscribers.get(msg_type, []):
                try:
                    cb(msg)
                except Exception as e:
                    print(f"[PixIPC] Erreur callback {msg_type}: {e}")

            # Wildcard subscribers
            for cb in self._subscribers.get("*", []):
                try:
                    cb(msg)
                except Exception as e:
                    print(f"[PixIPC] Erreur callback *: {e}")

        return msg

    def subscribe(self, msg_type: str, callback: Callable):
        """S'abonner à un type de message."""
        with self._lock:
            self._subscribers[msg_type].append(callback)

    def unsubscribe(self, msg_type: str, callback: Callable):
        """Se désabonner."""
        with self._lock:
            if callback in self._subscribers.get(msg_type, []):
                self._subscribers[msg_type].remove(callback)

    def get_log(self, msg_type: str = None, limit: int = 50) -> list[dict]:
        """Récupérer l'historique des messages."""
        with self._lock:
            msgs = self._message_log[-limit:]
        if msg_type:
            msgs = [m for m in msgs if m["type"] == msg_type]
        return msgs

    def stats(self) -> dict:
        with self._lock:
            by_type = defaultdict(int)
            for msg in self._message_log:
                by_type[msg["type"]] += 1
            return {
                "total_messages": self._message_count,
                "by_type": dict(by_type),
                "subscribers": {
                    k: len(v) for k, v in self._subscribers.items()
                },
                "log_size": len(self._message_log),
            }


# ── Singleton ───────────────────────────────────────────────

bus = PixIPC()

__all__ = ["PixIPC", "bus"]
