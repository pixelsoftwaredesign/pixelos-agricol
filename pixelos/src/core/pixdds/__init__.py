"""
PixDDS — Data Distribution Service pour Pixel OS.

Couche de communication distribuée inspirée du standard OMG DDS.
Permet aux robots d'un essaim de s'échanger des données en temps réel
via des topics typés avec QoS.

Architecture :
  DomainParticipant (1 par robot)
    ├── Topic (data channel, ex: "/swarm/position")
    ├── DataWriter (publie sur un topic)
    └── DataReader (souscrit à un topic, callback)

Transport :
  - InProcess : simulation multi-robot dans un même processus
  - UDP multicast : réseau local (prêt pour OpenBSD)
  - FastDDS : futur remplacement natif

Usage :
    from core.pixdds import create_participant

    node = create_participant(domain_id=0, node_id="robot_01")
    topic = node.create_topic("/swarm/position")
    writer = node.create_writer(topic)
    reader = node.create_reader(topic, callback=on_pos)
    writer.write({"x": 12.5, "y": 45.2})
"""

from .domain import DomainParticipant
from .qos import DomainQoS
from .topic import Topic, TopicQoS
from .writer import DataWriter
from .reader import DataReader
from .transport import InProcessTransport, get_transport, set_transport
from .discovery import PeerDiscovery, PeerInfo


def create_participant(domain_id: int = 0,
                       node_id: str = None,
                       qos: DomainQoS = None) -> DomainParticipant:
    """Factory : crée un participant DDS avec transport auto-détecté."""
    transport = get_transport()
    return DomainParticipant(domain_id, node_id, transport, qos)


__all__ = [
    "DomainParticipant", "DomainQoS",
    "Topic", "TopicQoS",
    "DataWriter", "DataReader",
    "InProcessTransport", "get_transport", "set_transport",
    "PeerDiscovery", "PeerInfo",
    "create_participant",
]
