#!/usr/bin/env python3
"""
Bootloader Zero-Touch PixelOS.

Au premier démarrage d'un robot :
  1. Découvre l'Orchestrateur sur le réseau (UDP broadcast)
  2. Demande sa configuration (IP, Node ID, clés PixNet)
  3. S'auto-configure et rejoint la flotte
  4. Enregistre le module auprès du bus IPC

Usage :
  python3 installer/bootloader.py [--force]

Sans --force, le bootloader vérifie si /etc/pixelos/node_id existe
et passe son tour si le nœud est déjà configuré.
"""

import os
import sys
import json
import time
import socket
import struct
import hashlib
import platform
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pixelos", "src"))

PIXOS_DISCOVER_PORT = 8337
PIXOS_DISCOVER_MAGIC = b"PIXOS_DISCOVER_V1"
PIXOS_ANSWER_MAGIC = b"PIXOS_ANSWER_V1"
BROADCAST_ADDR = "255.255.255.255"
DISCOVER_INTERVAL = 5.0
DISCOVER_RETRIES = 12
JOIN_TIMEOUT = 30.0
CONFIG_DIR = "/etc/pixelos"
PIXNET_DIR = "/etc/pixnet"
NODE_ID_FILE = "node_id"
NODE_KEY_FILE = "node_key"
NODE_CONFIG_FILE = "config.json"
LOG_DIR = "/var/log/pixelos"
BOOTSTRAP_LOG = "bootloader.log"
STATE_FILE = "/var/db/pixelos/bootloader_state.json"


class BootloaderError(Exception):
    pass


def log(msg: str):
    line = f"[{datetime.now().isoformat()}] {msg}"
    print(line, flush=True)
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    with open(Path(LOG_DIR) / BOOTSTRAP_LOG, "a") as f:
        f.write(line + "\n")


def hardware_id() -> str:
    """Génère un identifiant matériel unique et stable."""
    parts = []
    try:
        with open("/sys/class/net/eth0/address") as f:
            parts.append(f.read().strip())
    except Exception:
        pass
    try:
        with open("/sys/class/net/wlan0/address") as f:
            parts.append(f.read().strip())
    except Exception:
        parts.append(str(uuid.getnode()))

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    parts.append(line.split(":")[-1].strip())
                    break
    except Exception:
        pass

    raw = "-".join(parts) or socket.gethostname()
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def orch_ip_from_url(url: str) -> str:
    """Extrait l'IP d'une URL d'orchestrateur."""
    url = url.replace("http://", "").replace("https://", "")
    host = url.split(":")[0]
    return host


def is_already_configured() -> bool:
    path = Path(CONFIG_DIR) / NODE_ID_FILE
    if path.exists():
        node_id = path.read_text().strip()
        log(f"Node already configured: {node_id}")
        return True
    return False


def save_state(state: dict):
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"phase": "init", "retries": 0, "last_error": ""}


# ── Phase 1 : Découverte réseau (UDP broadcast) ──────────

def discover_orchestrator(timeout: float = 60.0) -> str:
    """
    Envoie des broadcasts UDP sur PixOS_DISCOVER_PORT.
    Retourne l'URL de l'Orchestrateur détecté.
    Lève BootloaderError si aucun orchestrateur trouvé.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(DISCOVER_INTERVAL)
    sock.bind(("0.0.0.0", 0))

    hw_id = hardware_id()
    hostname = socket.gethostname()
    discover_payload = json.dumps({
        "type": "discover",
        "hw_id": hw_id,
        "hostname": hostname,
        "arch": platform.machine(),
        "os": platform.system(),
    }).encode()

    deadline = time.time() + timeout
    attempt = 0

    log(f"Discovering orchestrator (timeout={timeout}s, hw_id={hw_id[:16]}...)")

    while time.time() < deadline:
        attempt += 1
        try:
            sock.sendto(PIXOS_DISCOVER_MAGIC + discover_payload,
                        (BROADCAST_ADDR, PIXOS_DISCOVER_PORT))
            log(f"Discovery broadcast #{attempt}")
        except Exception as e:
            log(f"Broadcast error: {e}")

        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
                if data.startswith(PIXOS_ANSWER_MAGIC):
                    answer = json.loads(data[len(PIXOS_ANSWER_MAGIC):])
                    orch_url = answer.get("orchestrator_url", "")
                    if orch_url:
                        log(f"Orchestrator found at {orch_url} (from {addr[0]})")
                        sock.close()
                        return orch_url
            except socket.timeout:
                break
            except Exception as e:
                log(f"Recv error: {e}")

    sock.close()
    raise BootloaderError(
        f"No orchestrator found after {attempt} attempts ({timeout}s)"
    )


# ── Phase 2 : Demande de configuration HTTP ──────────────

def _pixkey_auth() -> dict:
    """Tente une authentification via PixKey (YubiKey / token / recovery)."""
    try:
        from core.pixkey.pixkey import PixKey
        pk = PixKey()

        # YubiKey d'abord
        if pk.yubikey_available:
            result = pk.authenticate("yubikey")
            if result.get("authenticated"):
                return {"method": "yubikey", "token": result.get("info", "yubikey")[:64]}

        # Token ensuite
        for t in pk.keys.get("tokens", []):
            result = pk.authenticate("token", token=t["id"])
            if result.get("authenticated"):
                return {"method": "token", "token": t["id"]}

        return {"method": "none", "token": ""}
    except Exception:
        return {"method": "none", "token": ""}


def join_orchestrator(orch_url: str) -> dict:
    """
    Envoie une requête de join à l'Orchestrateur avec authentification PixKey.
    Retourne la configuration attribuée (node_id, ip, pixnet_key, ...).
    """
    hw_id = hardware_id()
    hostname = socket.gethostname()
    auth = _pixkey_auth()
    join_payload = {
        "hw_id": hw_id,
        "hostname": hostname,
        "mac_addresses": [],
        "arch": platform.machine(),
        "os": platform.system(),
        "python_version": sys.version.split()[0],
        "pixkey_auth": auth,
    }

    try:
        with open("/sys/class/net/eth0/address") as f:
            join_payload["mac_addresses"].append(f.read().strip())
    except Exception:
        pass

    log(f"Joining orchestrator at {orch_url}")

    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        f"{orch_url.rstrip('/')}/api/orchestrator/node/join",
        data=json.dumps(join_payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "PixelOS-Bootloader/2.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=JOIN_TIMEOUT) as resp:
            config = json.loads(resp.read().decode())
            if config.get("status") == "ok" and config.get("node_id"):
                log(f"Joined fleet as node {config['node_id']}")
                return config
            raise BootloaderError(
                f"Join rejected: {config.get('error', 'unknown')}"
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise BootloaderError(f"HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise BootloaderError(f"Connection failed: {e.reason}")


# ── Phase 3 : Application de la configuration ────────────

def apply_config(config: dict):
    """Applique la configuration reçue de l'Orchestrateur."""
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    Path(PIXNET_DIR).mkdir(parents=True, exist_ok=True)

    node_id = config.get("node_id", "")
    ip_address = config.get("ip_address", "")
    pixnet_key = config.get("pixnet_key", "")
    module_config = config.get("config", {})

    if node_id:
        Path(CONFIG_DIR, NODE_ID_FILE).write_text(node_id + "\n")
        Path(PIXNET_DIR, NODE_ID_FILE).write_text(node_id + "\n")
        os.chmod(Path(CONFIG_DIR, NODE_ID_FILE), 0o644)
        log(f"Node ID: {node_id}")

    if pixnet_key:
        key_path = Path(PIXNET_DIR, NODE_KEY_FILE)
        key_path.write_text(pixnet_key + "\n")
        os.chmod(key_path, 0o600)
        log("PixNet key written")

    if not pixnet_key:
        log("No PixNet key from orchestrator — generating local keypair")
        key = hashlib.sha256(
            f"{node_id}{os.urandom(32).hex()}".encode()
        ).hexdigest()
        Path(PIXNET_DIR, NODE_KEY_FILE).write_text(key + "\n")
        os.chmod(Path(PIXNET_DIR, NODE_KEY_FILE), 0o600)

    full_config = {
        "node_id": node_id,
        "ip_address": ip_address,
        "hostname": config.get("hostname", socket.gethostname()),
        "orchestrator": config.get("orchestrator_url", ""),
        "modules": module_config,
        "configured_at": datetime.now(timezone.utc).isoformat(),
        "bootloader_version": "2.0",
    }

    config_path = Path(CONFIG_DIR, NODE_CONFIG_FILE)
    config_path.write_text(json.dumps(full_config, indent=2))
    os.chmod(config_path, 0o644)
    log(f"Config written to {config_path}")

    if ip_address:
        _apply_ip_address(ip_address)

    return full_config


def _apply_ip_address(ip: str):
    """Configure l'adresse IP sur l'interface principale."""
    try:
        subprocess.run(
            ["ip", "addr", "add", ip, "dev", "eth0"],
            capture_output=True, text=True, timeout=10,
        )
        log(f"IP {ip} configured on eth0")
    except Exception as e:
        log(f"IP configuration skipped: {e}")


# ── Phase 4 : Enregistrement IPC + confirmation ──────────

def register_with_ipc(node_id: str):
    """Enregistre le module bootloader auprès du bus IPC."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pixelos", "src"))
        from core.ipc import MessageBus, PixModule, MSG_TYPE_REGISTER
        from core.ipc import Message

        bus = MessageBus()
        bus.start()

        mod = PixModule("bootloader", version="2.0")
        mod.register({
            "node_id": node_id,
            "type": "system",
            "hardware_id": hardware_id(),
        })
        mod.send_heartbeat_loop(interval=30)
        log("Bootloader registered on IPC bus")
    except Exception as e:
        log(f"IPC registration skipped: {e}")


def confirm_join(orch_url: str, node_id: str):
    """Confirme l'adhésion auprès de l'Orchestrateur."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"{orch_url.rstrip('/')}/api/orchestrator/node/{node_id}/confirm",
            data=json.dumps({
                "node_id": node_id,
                "hostname": socket.gethostname(),
                "hw_id": hardware_id(),
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            log(f"Join confirmed: {result.get('status', 'ok')}")
            return result
    except Exception as e:
        log(f"Confirm warning: {e}")
        return {"status": "warning", "error": str(e)}


# ── Orchestrateur principal ───────────────────────────────

def run(force: bool = False) -> dict:
    start = time.time()
    state = load_state()

    if not force and is_already_configured():
        return {"status": "skipped", "reason": "already configured",
                "node_id": Path(CONFIG_DIR, NODE_ID_FILE).read_text().strip()}

    log("=== PixelOS Zero-Touch Bootloader ===")
    log(f"Hardware ID: {hardware_id()[:16]}...")
    log(f"Hostname: {socket.gethostname()}")
    log(f"Platform: {platform.system()} {platform.machine()}")
    log(f"Python: {sys.version.split()[0]}")

    # Phase 0 : Vérification d'intégrité au démarrage
    log("Phase 0/5: Boot integrity check")
    try:
        from core.security.boot_integrity import check_boot_integrity, find_project_root
        integrity = check_boot_integrity(find_project_root())
        if not integrity["passed"]:
            log(f"INTEGRITY FAILED: {integrity.get('error', 'hash mismatch')}")
            log("WARNING: Continuing in degraded mode (signature mismatch)")
            state["integrity_warning"] = True
        else:
            log(f"Integrity OK ({integrity['total_expected']} files)")
            state["integrity_warning"] = False
        save_state(state)
    except Exception as e:
        log(f"Integrity check skipped: {e}")

    try:
        # Phase 1 : Découverte
        log("Phase 1/4: Network discovery")
        orch_url = discover_orchestrator()
        state["phase"] = "discovered"
        state["orchestrator_url"] = orch_url
        save_state(state)

        # Phase 2 : Join
        log("Phase 2/4: Joining fleet")
        config = join_orchestrator(orch_url)
        node_id = config.get("node_id", "")
        state["phase"] = "joined"
        state["node_id"] = node_id
        save_state(state)

        # Phase 3 : Configuration
        log("Phase 3/4: Applying configuration")
        full_config = apply_config(config)

        # Phase 3b : Application des règles de pare-feu robot
        log("Phase 3b/5: Applying robot firewall rules")
        try:
            from core.security.robot_firewall import RobotFirewall
            fw = RobotFirewall(orch_ip=orch_ip_from_url(orch_url))
            fw_result = fw.apply()
            log(f"Firewall: {fw_result['status']}")
        except Exception as e:
            log(f"Firewall skipped: {e}")

        # Phase 4 : Confirmation
        log("Phase 4/5: Registration & confirmation")
        register_with_ipc(node_id)
        confirm_join(orch_url, node_id)

        elapsed = time.time() - start
        result = {
            "status": "ok",
            "node_id": node_id,
            "orchestrator": orch_url,
            "config": full_config,
            "elapsed_seconds": round(elapsed, 1),
        }
        log(f"Boot complete in {elapsed:.1f}s — node {node_id}")
        state["phase"] = "complete"
        state["result"] = result
        save_state(state)
        return result

    except BootloaderError as e:
        log(f"FAILED: {e}")
        state["phase"] = "error"
        state["last_error"] = str(e)
        state["retries"] = state.get("retries", 0) + 1
        save_state(state)
        return {"status": "error", "error": str(e), "phase": state["phase"]}

    except Exception as e:
        log(f"UNEXPECTED ERROR: {e}")
        state["phase"] = "error"
        state["last_error"] = str(e)
        save_state(state)
        return {"status": "error", "error": str(e), "phase": state["phase"]}


def listen_mode():
    """
    Mode écoute : l'Orchestrateur répond aux découvertes UDP.
    À lancer sur le nœud Orchestrateur (en complément du serveur web).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", PIXOS_DISCOVER_PORT))
    sock.settimeout(1.0)

    orch_url = os.environ.get(
        "PIXOS_ORCHESTRATOR_URL",
        f"http://{socket.gethostname()}:8080",
    )

    log(f"Bootloader listen mode active on port {PIXOS_DISCOVER_PORT}")
    log(f"Advertising orchestrator at {orch_url}")

    answer = PIXOS_ANSWER_MAGIC + json.dumps({
        "type": "offer",
        "orchestrator_url": orch_url,
        "hostname": socket.gethostname(),
    }).encode()

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            if data.startswith(PIXOS_DISCOVER_MAGIC):
                try:
                    payload = json.loads(data[len(PIXOS_DISCOVER_MAGIC):])
                    hw = payload.get("hw_id", "unknown")[:16]
                    log(f"Discovery from {addr[0]} (hw={hw}...)")
                    sock.sendto(answer, addr)
                except Exception:
                    pass
        except socket.timeout:
            continue
        except Exception as e:
            log(f"Listen error: {e}")


def main():
    args = set(sys.argv[1:])
    force = "--force" in args
    listen = "--listen" in args

    if listen:
        listen_mode()
        return

    result = run(force=force)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
