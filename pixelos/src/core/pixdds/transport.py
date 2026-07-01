"""
PixDDS — Transport de données.

InProcessTransport : simulation multi-robot dans un même processus.
UdpTransport : UDP multicast pour réseau local (futur).
"""

import json
import threading
import time
from collections import defaultdict
from typing import Any, Optional
from .topic import TopicData

# ── Dispatch global (pont Writer → Reader) ──────────────────

_SUBSCRIBERS: dict[str, list] = defaultdict(list)  # topic_name → [(domain, reader)]
_LOCK = threading.Lock()


def _dispatch(topic_name: str, domain_id: int, sample: TopicData):
    """Distribuer un échantillon à tous les lecteurs abonnés."""
    with _LOCK:
        for sub_topic, readers in _SUBSCRIBERS.items():
            if sub_topic == topic_name:
                for reader_domain, reader in readers:
                    if reader_domain == domain_id:
                        reader.on_data(sample)


def _subscribe(topic_name: str, domain_id: int, reader):
    with _LOCK:
        _SUBSCRIBERS[topic_name].append((domain_id, reader))


def _unsubscribe(topic_name: str, domain_id: int, reader):
    with _LOCK:
        subs = _SUBSCRIBERS.get(topic_name, [])
        _SUBSCRIBERS[topic_name] = [
            (d, r) for d, r in subs if not (d == domain_id and r is reader)
        ]


# ── Transport abstrait ──────────────────────────────────────

class Transport:
    """Classe de base pour un transport DDS."""

    def __init__(self, transport_id: str = "inprocess"):
        self.transport_id = transport_id

    def register_reader(self, topic_name: str, domain_id: int, reader):
        raise NotImplementedError

    def unregister_reader(self, topic_name: str, domain_id: int, reader):
        raise NotImplementedError

    def __repr__(self):
        return f"Transport({self.transport_id})"


class InProcessTransport(Transport):
    """Transport en mémoire : partage global dans le processus.

    Permet de simuler plusieurs robots DDS dans un seul test.
    Les messages sont dispatchés instantanément.
    """

    def __init__(self):
        super().__init__("inprocess")

    def register_reader(self, topic_name: str, domain_id: int, reader):
        _subscribe(topic_name, domain_id, reader)

    def unregister_reader(self, topic_name: str, domain_id: int, reader):
        _unsubscribe(topic_name, domain_id, reader)


# ── Singleton transport ─────────────────────────────────────

_TRANSPORT: Optional[Transport] = None


def get_transport() -> Transport:
    global _TRANSPORT
    if _TRANSPORT is None:
        _TRANSPORT = InProcessTransport()
    return _TRANSPORT


def set_transport(t: Transport):
    global _TRANSPORT
    _TRANSPORT = t


__all__ = [
    "Transport", "InProcessTransport",
    "get_transport", "set_transport",
    "_subscribe", "_unsubscribe", "_dispatch",
]
