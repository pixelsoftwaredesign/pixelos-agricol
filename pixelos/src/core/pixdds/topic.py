"""
PixDDS — Topic (canal de données typé).
"""

import time
from dataclasses import dataclass, field
from typing import Any
from .qos import TopicQoS, DEFAULT_TOPIC_QOS


@dataclass
class TopicData:
    """Échantillon de données publié sur un topic."""
    topic_name: str
    source_node: str
    data: Any
    timestamp: float = 0.0
    sequence: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.monotonic()


class Topic:
    """Canal de données nommé dans un domaine DDS."""

    def __init__(self, name: str, domain_id: int,
                 qos: TopicQoS = None):
        self.name = name
        self.domain_id = domain_id
        self.qos = qos or DEFAULT_TOPIC_QOS
        self._writers: list = []
        self._readers: list = []
        self._last_sequence = 0

    def _next_seq(self) -> int:
        self._last_sequence += 1
        return self._last_sequence

    def attach_writer(self, writer):
        if writer not in self._writers:
            self._writers.append(writer)

    def detach_writer(self, writer):
        if writer in self._writers:
            self._writers.remove(writer)

    def attach_reader(self, reader):
        if reader not in self._readers:
            self._readers.append(reader)

    def detach_reader(self, reader):
        if reader in self._readers:
            self._readers.remove(reader)

    @property
    def writer_count(self) -> int:
        return len(self._writers)

    @property
    def reader_count(self) -> int:
        return len(self._readers)

    def __repr__(self):
        return (f"Topic({self.name}, domain={self.domain_id}, "
                f"writers={self.writer_count}, readers={self.reader_count})")
