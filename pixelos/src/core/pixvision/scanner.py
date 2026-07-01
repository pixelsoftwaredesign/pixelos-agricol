"""
PixVision — Scanner réseau IoT.

Identify connected objects via:
  - ARP scanning / ARP table parsing
  - TCP port scanning (active fingerprint)
  - mDNS / NetBIOS name discovery
  - MAC OUI lookup

Designed for OpenBSD with libpcap, but has a full Python fallback
(ARP table + socket scanning) for development on any platform.
"""

import ipaddress
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .oui_db import lookup_oui, is_iot_likely

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pixvision"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEVICES_FILE = DATA_DIR / "devices.json"

# ── Models ──────────────────────────────────────────────────

@dataclass
class NetworkDevice:
    mac: str
    ip: str
    hostname: str = ""
    manufacturer: str = ""
    device_type: str = "inconnu"
    confidence: float = 0.0
    rssi: int = -100
    open_ports: list = field(default_factory=list)
    services: dict = field(default_factory=dict)
    protocol: str = "wifi"
    first_seen: str = ""
    last_seen: str = ""
    status: str = "online"

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return NetworkDevice(**d)


# ── OUI cache ───────────────────────────────────────────────

_OUI_CACHE = {}


def _resolve_oui(mac: str) -> dict:
    if mac not in _OUI_CACHE:
        _OUI_CACHE[mac] = lookup_oui(mac)
    return _OUI_CACHE[mac]


# ── Network scanner ─────────────────────────────────────────

class NetworkScanner:
    """Scans local network for IoT devices.

    Uses platform-appropriate methods:
      - Windows: arp -a, TCP sockets, mDNS
      - Linux/OpenBSD: /proc/net/arp, raw sockets
    """

    def __init__(self, interface: str = None):
        self.interface = interface
        self._devices: dict[str, NetworkDevice] = {}
        self._lock = threading.Lock()
        self._load_devices()
        self._local_net = self._detect_local_network()

    # ── Persistence ─────────────────────────────────────────

    def _load_devices(self):
        if DEVICES_FILE.exists():
            try:
                data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
                for d in data:
                    dev = NetworkDevice.from_dict(d)
                    self._devices[dev.mac] = dev
            except Exception:
                pass

    def _save_devices(self):
        with self._lock:
            data = [d.to_dict() for d in self._devices.values()]
            DEVICES_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _upsert_device(self, dev: NetworkDevice):
        key = dev.mac
        with self._lock:
            if key in self._devices:
                existing = self._devices[key]
                existing.ip = dev.ip
                existing.last_seen = dev.last_seen
                existing.rssi = dev.rssi or existing.rssi
                if dev.hostname:
                    existing.hostname = dev.hostname
                if dev.open_ports:
                    existing.open_ports = sorted(set(existing.open_ports + dev.open_ports))
                if dev.services:
                    existing.services.update(dev.services)
                existing.status = "online"
            else:
                self._devices[key] = dev

    # ── Local network detection ─────────────────────────────

    def _detect_local_network(self) -> str:
        """Detect local network CIDR (e.g. 192.168.1.0/24)."""
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    "ipconfig", shell=True, text=True, stderr=subprocess.DEVNULL
                )
                ip_match = re.search(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", out)
                mask_match = re.search(r"Mask[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", out)
                if ip_match and mask_match:
                    ip = ip_match.group(1)
                    mask = mask_match.group(1)
                    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                    return str(net)
            except Exception:
                pass
        else:
            try:
                out = subprocess.check_output(
                    ["ip", "-o", "-4", "addr", "show"],
                    text=True, stderr=subprocess.DEVNULL
                )
                m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+/\d+)", out)
                if m:
                    return m.group(1)
            except Exception:
                pass
        return "192.168.1.0/24"

    # ── Core scan methods ───────────────────────────────────

    def _arp_scan(self) -> list[NetworkDevice]:
        """Parse ARP table for active devices."""
        devices = []
        now = datetime.now(timezone.utc).isoformat()

        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    "arp -a", shell=True, text=True, stderr=subprocess.DEVNULL
                )
                for line in out.splitlines():
                    m = re.match(
                        r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]+)\s+",
                        line
                    )
                    if m:
                        ip = m.group(1)
                        mac = m.group(2).replace("-", ":")
                        if mac.count(":") == 5 and ip != "224.0.0.22":
                            oui_info = _resolve_oui(mac)
                            dev = NetworkDevice(
                                mac=mac.upper(),
                                ip=ip,
                                manufacturer=oui_info["manufacturer"],
                                device_type=oui_info["device_type"],
                                confidence=oui_info["confidence"],
                                first_seen=now,
                                last_seen=now,
                                protocol="wifi",
                            )
                            devices.append(dev)
            except Exception:
                pass
        else:
            try:
                with open("/proc/net/arp") as f:
                    for line in f.readlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                            ip = parts[0]
                            mac = parts[3]
                            oui_info = _resolve_oui(mac)
                            dev = NetworkDevice(
                                mac=mac.upper(), ip=ip,
                                manufacturer=oui_info["manufacturer"],
                                device_type=oui_info["device_type"],
                                confidence=oui_info["confidence"],
                                first_seen=now, last_seen=now,
                            )
                            devices.append(dev)
            except Exception:
                pass

        return devices

    def _port_scan(self, ip: str, ports: list = None) -> list[int]:
        """Quick TCP connect scan on common IoT ports."""
        if ports is None:
            ports = [22, 80, 443, 502, 1883, 8883, 5683, 5684,
                     8080, 8443, 9090, 2404, 2455, 1024, 5000]
        open_ports = []
        for port in ports:
            try:
                with socket.create_connection((ip, port), timeout=0.5):
                    open_ports.append(port)
            except (OSError, socket.timeout):
                pass
        return open_ports

    def _resolve_hostname(self, ip: str) -> str:
        """Reverse DNS lookup."""
        try:
            host, _, _ = socket.gethostbyaddr(ip)
            return host
        except Exception:
            return ""

    def _mdns_discover(self, timeout: float = 2.0) -> list[dict]:
        """Multicast DNS query for _services._dns-sd._udp.local."""
        results = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            sock.settimeout(timeout)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            # Simple mDNS query for A records
            qname = b"\x05_local\x04arpa\x00\x00\x01\x00\x01"
            # Just use socket to detect mDNS responders
            sock.sendto(qname, ("224.0.0.251", 5353))
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    ip = addr[0]
                    if ip not in [r["ip"] for r in results]:
                        results.append({"ip": ip, "via": "mDNS"})
                except socket.timeout:
                    break
            sock.close()
        except Exception:
            pass
        return results

    # ── Main scan ──────────────────────────────────────────

    def scan(self, deep: bool = False) -> dict:
        """Run full network scan.

        Args:
            deep: If True, also do port scanning on each discovered device.

        Returns:
            dict with scan results, new devices, timing.
        """
        start_time = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()

        # ARP scan
        arp_devices = self._arp_scan()
        for dev in arp_devices:
            dev.last_seen = now
            if not dev.first_seen:
                dev.first_seen = now
            self._upsert_device(dev)

        # mDNS discovery for additional hosts
        mdns_hosts = self._mdns_discover()
        for entry in mdns_hosts:
            ip = entry["ip"]
            mac = self._ip_to_mac(ip)
            if mac:
                oui_info = _resolve_oui(mac)
                dev = NetworkDevice(
                    mac=mac.upper(), ip=ip,
                    manufacturer=oui_info["manufacturer"],
                    device_type=oui_info["device_type"],
                    confidence=oui_info["confidence"],
                    first_seen=now, last_seen=now, protocol="wifi",
                )
                self._upsert_device(dev)

        # Deep scan: port + hostname resolution
        new_fingerprints = 0
        if deep:
            for mac, dev in list(self._devices.items()):
                if dev.status != "online":
                    continue
                # Resolve hostname
                if not dev.hostname:
                    dev.hostname = self._resolve_hostname(dev.ip)
                # Port scan
                ports = self._port_scan(dev.ip)
                if ports:
                    new_fingerprints += 1
                    dev.open_ports = sorted(set(dev.open_ports + ports))
                    self._classify_by_ports(dev)

        # Mark stale devices
        self._mark_stale(now)

        self._save_devices()

        elapsed = time.monotonic() - start_time
        with self._lock:
            total = len(self._devices)
            online = sum(1 for d in self._devices.values() if d.status == "online")

        return {
            "total_devices": total,
            "online": online,
            "new_fingerprints": new_fingerprints,
            "elapsed_s": round(elapsed, 2),
            "timestamp": now,
        }

    # ── Helpers ─────────────────────────────────────────────

    def _ip_to_mac(self, ip: str) -> Optional[str]:
        """Try to get MAC for an IP from the ARP table."""
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    f"arp -a {ip}", shell=True, text=True, stderr=subprocess.DEVNULL
                )
                m = re.search(r"([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})", out)
                if m:
                    return m.group(1).replace("-", ":")
            except Exception:
                pass
        return None

    def _classify_by_ports(self, dev: NetworkDevice):
        """Refine device type based on open ports."""
        ports = set(dev.open_ports)
        classifications = {
            502: ("automate", 0.7),
            1883: ("iot_broker", 0.8),
            8883: ("iot_broker_secure", 0.8),
            5683: ("coap_device", 0.8),
            5684: ("coap_device_secure", 0.8),
            22: ("administration", 0.3),
            80: ("serveur_web", 0.3),
            443: ("serveur_web_secure", 0.3),
        }
        for port, (dtype, conf) in classifications.items():
            if port in ports and conf > dev.confidence:
                dev.device_type = dtype
                dev.confidence = conf

    def _mark_stale(self, now: str):
        """Mark devices not seen recently as stale."""
        try:
            now_dt = datetime.fromisoformat(now)
        except Exception:
            return
        for dev in self._devices.values():
            if dev.last_seen:
                try:
                    seen = datetime.fromisoformat(dev.last_seen)
                    if (now_dt - seen).total_seconds() > 3600:
                        dev.status = "stale"
                except Exception:
                    pass

    # ── Public API ─────────────────────────────────────────

    def get_devices(self, status: str = None) -> list[dict]:
        with self._lock:
            devs = list(self._devices.values())
        if status:
            devs = [d for d in devs if d.status == status]
        return [d.to_dict() for d in sorted(devs, key=lambda x: x.last_seen or "", reverse=True)]

    def get_device(self, mac: str) -> Optional[dict]:
        with self._lock:
            dev = self._devices.get(mac.upper())
        return dev.to_dict() if dev else None

    def identify_device(self, mac: str, device_type: str, manufacturer: str = "") -> dict:
        mac = mac.upper()
        with self._lock:
            if mac in self._devices:
                dev = self._devices[mac]
                dev.device_type = device_type
                if manufacturer:
                    dev.manufacturer = manufacturer
                dev.confidence = 1.0
                self._save_devices()
                return dev.to_dict()
        return {"error": "not_found"}

    def remove_device(self, mac: str) -> dict:
        mac = mac.upper()
        with self._lock:
            if mac in self._devices:
                del self._devices[mac]
                self._save_devices()
                return {"removed": True}
        return {"error": "not_found"}

    def stats(self) -> dict:
        with self._lock:
            total = len(self._devices)
            by_type = {}
            by_status = {}
            for d in self._devices.values():
                by_type[d.device_type] = by_type.get(d.device_type, 0) + 1
                by_status[d.status] = by_status.get(d.status, 0) + 1
            return {
                "total": total,
                "by_type": by_type,
                "by_status": by_status,
                "last_scan": DEVICES_FILE.stat().st_mtime if DEVICES_FILE.exists() else 0,
                "local_network": self._local_net,
            }

    def oui_lookup(self, mac: str) -> dict:
        return _resolve_oui(mac.upper())


# ── Singleton ───────────────────────────────────────────────

scanner = NetworkScanner()

__all__ = [
    "NetworkScanner", "NetworkDevice", "scanner",
]
