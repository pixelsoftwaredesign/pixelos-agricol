"""
PixDDS — QoS et configuration.
"""

from dataclasses import dataclass
from enum import IntEnum


class ReliabilityKind(IntEnum):
    BEST_EFFORT = 0
    RELIABLE = 1


class DurabilityKind(IntEnum):
    VOLATILE = 0
    TRANSIENT_LOCAL = 1
    TRANSIENT = 2
    PERSISTENT = 3


class HistoryKind(IntEnum):
    KEEP_LAST = 0
    KEEP_ALL = 1


@dataclass
class TopicQoS:
    reliability: ReliabilityKind = ReliabilityKind.BEST_EFFORT
    durability: DurabilityKind = DurabilityKind.VOLATILE
    history: HistoryKind = HistoryKind.KEEP_LAST
    history_depth: int = 10
    deadline_ms: int = 0
    lifespan_ms: int = 0
    priority: int = 0


@dataclass
class DomainQoS:
    heartbeat_ms: int = 1000
    discovery_timeout_s: int = 10
    max_participants: int = 100
    transport: str = "auto"


DEFAULT_TOPIC_QOS = TopicQoS()
DEFAULT_DOMAIN_QOS = DomainQoS()
