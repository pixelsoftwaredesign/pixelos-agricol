#!/usr/bin/env python3
"""
PixOrchestrator – Cerveau distribué de la flotte robotique.
- Écoute les heartbeats des pairs (UDP)
- Maintient PEERS_STATE
- Détecte les nœuds défaillants
- Propose et exécute le failover avec vote majoritaire
"""

import socket
import json
import time
import threading
import base64
from datetime import datetime, timezone
from nacl.signing import SigningKey, VerifyKey
import os

HEARTBEAT_PORT = 9100
VOTE_PORT = 9101
HEARTBEAT_TIMEOUT = 180      # 3 minutes
CRITICAL_TIMEOUT = 60        # 1 minute warning
FANOUT = 3
GOSSIP_TTL = 5

MY_NODE_ID = open("/etc/pixnet/node_id").read().strip()
with open("/etc/pixnet/node_key", "rb") as f:
    signing_key = SigningKey(f.read())
verify_keys = {}  # chargé dynamiquement ou via fichier autorisé

PEERS_STATE = {}  # peer_ip -> {"last_seen": timestamp, "metrics": {...}}


def load_verify_keys():
    path = "/etc/pixnet/authorized_keys"
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                ip, key_b64 = line.strip().split()
                verify_keys[ip] = VerifyKey(base64.b64decode(key_b64))


def verify_signature(payload: str, signature_b64: str, peer_ip: str) -> bool:
    if peer_ip not in verify_keys:
        return False
    try:
        verify_keys[peer_ip].verify(payload.encode(), base64.b64decode(signature_b64))
        return True
    except Exception:
        return False


def handle_heartbeat(data, addr):
    try:
        msg = json.loads(data.decode())
        payload = msg["payload"]
        if not verify_signature(payload, msg["signature"], addr[0]):
            return
        heartbeat = json.loads(payload)
        PEERS_STATE[addr[0]] = {
            "last_seen": time.time(),
            "metrics": heartbeat
        }
    except Exception as e:
        print(f"Heartbeat invalide de {addr}: {e}")


def request_vote(neighbor_ip, target_node):
    """Demande un vote pour prendre en charge target_node."""
    payload = {
        "type": "vote_request",
        "proposer": MY_NODE_ID,
        "target": target_node,
        "timestamp": time.time()
    }
    signed = signing_key.sign(json.dumps(payload).encode())
    msg = {
        "payload": payload,
        "signature": base64.b64encode(signed.signature).decode()
    }
    data = json.dumps(msg).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    try:
        sock.sendto(data, (neighbor_ip, VOTE_PORT))
        resp, _ = sock.recvfrom(1024)
        resp = json.loads(resp.decode())
        if verify_signature(json.dumps(resp["payload"]), resp["signature"], neighbor_ip):
            return resp.get("approve", False)
    except Exception:
        pass
    finally:
        sock.close()
    return False


def propose_takeover(peer_ip):
    votes_for = 1
    active = [
        ip for ip, s in PEERS_STATE.items()
        if ip != peer_ip and time.time() - s["last_seen"] < 300
    ]
    for ip in active:
        if request_vote(ip, peer_ip):
            votes_for += 1
    total = len(active) + 1
    return votes_for > total / 2


def take_over_tasks(peer_ip):
    print(f"Prise en charge des tâches de {peer_ip}")


def quarantine_node(peer_ip, reason):
    if peer_ip in PEERS_STATE:
        del PEERS_STATE[peer_ip]
    print(f"Nœud {peer_ip} isolé : {reason}")


def watchdog():
    while True:
        now = time.time()
        for ip, state in list(PEERS_STATE.items()):
            delta = now - state.get("last_seen", 0)
            if delta > HEARTBEAT_TIMEOUT:
                metrics = state.get("metrics", {})
                if metrics.get("energy_mode") == "critical":
                    if propose_takeover(ip):
                        take_over_tasks(ip)
                        quarantine_node(ip, "heartbeat timeout")
        time.sleep(30)


def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", HEARTBEAT_PORT))
    while True:
        data, addr = sock.recvfrom(4096)
        threading.Thread(target=handle_heartbeat, args=(data, addr)).start()


if __name__ == "__main__":
    load_verify_keys()
    threading.Thread(target=listener, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    while True:
        time.sleep(1)
