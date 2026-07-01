"""
PixDDS — Découverte de pairs (Peer Discovery).

UDP multicast sur 239.255.0.1:7400 pour annoncer sa présence
et découvrir les autres nœuds de l'essaim.
"""

import json
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

MCAST_GRP = "239.255.0.1"
MCAST_PORT = 7400
HEARTBEAT_SEC = 1.0
PEER_TIMEOUT_SEC = 10.0


@dataclass
class PeerInfo:
    node_id: str
    domain_id: int
    host: str = ""
    port: int = 0
    last_seen: float = 0.0
    first_seen: float = 0.0
    status: str = "online"  # online | stale | offline
    swarm_role: str = "unknown"  # drone | ground | gateway
    battery: int = -1
    load_avg: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "domain_id": self.domain_id,
            "host": self.host,
            "port": self.port,
            "last_seen": datetime.fromtimestamp(
                self.last_seen, tz=timezone.utc
            ).isoformat() if self.last_seen else "",
            "first_seen": datetime.fromtimestamp(
                self.first_seen, tz=timezone.utc
            ).isoformat() if self.first_seen else "",
            "status": self.status,
            "swarm_role": self.swarm_role,
            "battery": self.battery,
            "load_avg": round(self.load_avg, 2),
        }


class PeerDiscovery:
    """Découverte de pairs par UDP multicast.

    Envoie un heartbeat périodique et écoute les annonces des autres.
    """

    def __init__(self, node_id: str, domain_id: int = 0,
                 host: str = "", port: int = 0):
        self.node_id = node_id
        self.domain_id = domain_id
        self.host = host or self._get_local_ip()
        self.port = port
        self._peers: dict[str, PeerInfo] = {}
        self._lock = threading.Lock()
        self._running = False
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        if self._running:
            return
        self._running = True

        # Socket UDP multicast
        try:
            self._sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(0.5)
            mreq = struct.pack(
                "4sl",
                socket.inet_aton(MCAST_GRP),
                socket.INADDR_ANY
            )
            self._sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq
            )
            self._sock.bind(("", MCAST_PORT))

            # TTL pour les émissions
            self._sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2
            )
        except Exception as e:
            print(f"[PeerDiscovery] Socket error: {e}")
            self._sock = None

        # Thread d'écoute
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        # S'annoncer immédiatement
        self._announce()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _announce(self):
        """Envoyer un heartbeat UDP."""
        if not self._sock:
            return
        payload = json.dumps({
            "type": "PIXDDS_HEARTBEAT",
            "node_id": self.node_id,
            "domain_id": self.domain_id,
            "host": self.host,
            "port": self.port,
            "timestamp": time.monotonic(),
        }).encode()
        try:
            self._sock.sendto(payload, (MCAST_GRP, MCAST_PORT))
        except Exception:
            pass

    def _listen_loop(self):
        while self._running:
            self._announce()
            now = time.monotonic()

            # Lire les messages entrants
            if self._sock:
                while True:
                    try:
                        data, addr = self._sock.recvfrom(4096)
                        msg = json.loads(data.decode())
                        if msg.get("type") == "PIXDDS_HEARTBEAT":
                            nid = msg["node_id"]
                            if nid != self.node_id:
                                with self._lock:
                                    if nid in self._peers:
                                        p = self._peers[nid]
                                        p.last_seen = now
                                    else:
                                        self._peers[nid] = PeerInfo(
                                            node_id=nid,
                                            domain_id=msg.get("domain_id", 0),
                                            host=msg.get("host", addr[0]),
                                            port=msg.get("port", 0),
                                            last_seen=now,
                                            first_seen=now,
                                        )
                    except socket.timeout:
                        break
                    except Exception:
                        break

            # Marquer les pairs périmés
            with self._lock:
                for p in self._peers.values():
                    if p.status == "online" and \
                       (now - p.last_seen) > PEER_TIMEOUT_SEC:
                        p.status = "stale"

            time.sleep(HEARTBEAT_SEC)

    def get_peers(self) -> list[PeerInfo]:
        with self._lock:
            return list(self._peers.values())

    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        with self._lock:
            return self._peers.get(node_id)

    def peer_count(self) -> int:
        with self._lock:
            return len(self._peers)

    def stats(self) -> dict:
        with self._lock:
            online = sum(1 for p in self._peers.values()
                         if p.status == "online")
            return {
                "total": len(self._peers),
                "online": online,
                "stale": len(self._peers) - online,
            }
