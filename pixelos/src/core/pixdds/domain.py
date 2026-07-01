"""
PixDDS — DomainParticipant.

Point d'entrée principal : un participant DDS par robot.
Gère les topics, writers, readers et la découverte de pairs.
"""

import time
from typing import Any, Callable, Optional
from .qos import DomainQoS, TopicQoS, DEFAULT_DOMAIN_QOS, DEFAULT_TOPIC_QOS
from .topic import Topic
from .writer import DataWriter
from .reader import DataReader
from .transport import Transport, get_transport, _subscribe, _unsubscribe
from .discovery import PeerDiscovery


class DomainParticipant:
    """Participant DDS = un nœud dans l'essaim.

    Usage:
        node = DomainParticipant(domain_id=0, node_id="robot_01")
        topic = node.create_topic("/swarm/position")
        writer = node.create_writer(topic)
        reader = node.create_reader(topic, callback=my_cb)
        writer.write({"x": 12.5, "y": 45.2})
        node.close()
    """

    def __init__(self, domain_id: int = 0,
                 node_id: str = None,
                 transport: Transport = None,
                 qos: DomainQoS = None):
        self.domain_id = domain_id
        self.node_id = node_id or f"node_{id(self):x}"
        self.qos = qos or DEFAULT_DOMAIN_QOS
        self._transport = transport or get_transport()
        self._topics: dict[str, Topic] = {}
        self._writers: list[DataWriter] = []
        self._readers: list[DataReader] = []

        # Découverte de pairs
        self.discovery = PeerDiscovery(
            node_id=self.node_id,
            domain_id=domain_id,
        )
        self.discovery.start()

    # ── Topics ──────────────────────────────────────────────

    def create_topic(self, name: str,
                     qos: TopicQoS = None) -> Topic:
        """Créer ou retrouver un topic dans ce domaine."""
        key = f"{self.domain_id}:{name}"
        if key in self._topics:
            return self._topics[key]
        topic = Topic(name, self.domain_id, qos)
        self._topics[key] = topic
        return topic

    def delete_topic(self, topic: Topic):
        key = f"{self.domain_id}:{topic.name}"
        self._topics.pop(key, None)

    # ── Writers ─────────────────────────────────────────────

    def create_writer(self, topic: Topic) -> DataWriter:
        writer = DataWriter(topic, self.node_id)
        self._writers.append(writer)
        return writer

    def delete_writer(self, writer: DataWriter):
        writer.close()
        if writer in self._writers:
            self._writers.remove(writer)

    # ── Readers ─────────────────────────────────────────────

    def create_reader(self, topic: Topic,
                      callback: Callable = None) -> DataReader:
        reader = DataReader(topic, self.node_id, callback)
        self._transport.register_reader(topic.name, self.domain_id, reader)
        self._readers.append(reader)
        return reader

    def delete_reader(self, reader: DataReader):
        self._transport.unregister_reader(
            reader.topic.name, self.domain_id, reader
        )
        reader.close()
        if reader in self._readers:
            self._readers.remove(reader)

    # ── State ───────────────────────────────────────────────

    def get_topic(self, name: str) -> Optional[Topic]:
        key = f"{self.domain_id}:{name}"
        return self._topics.get(key)

    def get_peers(self):
        return self.discovery.get_peers()

    def status(self) -> dict:
        return {
            "node_id": self.node_id,
            "domain_id": self.domain_id,
            "topics": [t.name for t in self._topics.values()],
            "writers": len(self._writers),
            "readers": len(self._readers),
            "peers": self.discovery.peer_count(),
            "transport": str(self._transport),
        }

    # ── Cleanup ─────────────────────────────────────────────

    def close(self):
        for r in list(self._readers):
            self.delete_reader(r)
        for w in list(self._writers):
            self.delete_writer(w)
        self._topics.clear()
        self.discovery.stop()

    def __repr__(self):
        return (f"DomainParticipant(id={self.node_id}, "
                f"domain={self.domain_id}, "
                f"topics={len(self._topics)})")
