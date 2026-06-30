#!/usr/bin/env python3
"""
PixNet Query Engine – DHT spécialisée pour données temporelles et géolocalisées.
- Table de routage Kademlia simplifiée
- Annonce de fragments temporels
- Recherche par plage de temps + filtre de Bloom
"""

import hashlib
import random
import time
import socket
import json
import threading
from collections import defaultdict

PORT = 9102
K = 20
ALPHA = 3

MY_NODE_ID = open("/etc/pixnet/node_id").read().strip()
MY_IP = "127.0.0.1"

routing_table = []
local_fragments = defaultdict(list)


def distance(id1, id2):
    return int(id1, 16) ^ int(id2, 16)


def add_peer(node_id, ip, port, temporal_buckets=None):
    if not any(p['id'] == node_id for p in routing_table):
        routing_table.append({
            'id': node_id,
            'ip': ip,
            'port': port,
            'temporal_buckets': temporal_buckets or {},
            'last_seen': time.time()
        })


def find_closest(target_id, count=K):
    return sorted(routing_table, key=lambda p: distance(p['id'], target_id))[:count]


def advertise_fragment(sensor_id, start, end, fragment_hash):
    local_fragments[sensor_id].append((start, end, fragment_hash))
    for peer in find_closest(MY_NODE_ID, K):
        try:
            msg = {
                "type": "ADVERTISE",
                "node_id": MY_NODE_ID,
                "sensor_id": sensor_id,
                "time_range": {"start": start, "end": end},
                "fragment_hash": fragment_hash,
                "signature": "TODO"
            }
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(msg).encode(), (peer['ip'], PORT))
            sock.close()
        except Exception:
            pass


def handle_message(data, addr):
    msg = json.loads(data.decode())
    if msg.get("type") == "ADVERTISE":
        add_peer(msg["node_id"], addr[0], PORT, {
            msg["sensor_id"]: [msg["time_range"]]
        })
        print(f"Annonce reçue de {msg['node_id']}: {msg['sensor_id']}")
    elif msg.get("type") == "FIND_DATA":
        sensor = msg.get("sensor_id")
        if sensor in local_fragments:
            response = {
                "type": "PROVIDE_DATA",
                "fragments": [{"hash": h, "ip": MY_IP} for _, _, h in local_fragments[sensor]]
            }
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(response).encode(), addr)
            sock.close()


def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    while True:
        data, addr = sock.recvfrom(4096)
        threading.Thread(target=handle_message, args=(data, addr)).start()


if __name__ == "__main__":
    threading.Thread(target=listener, daemon=True).start()
    while True:
        time.sleep(60)
