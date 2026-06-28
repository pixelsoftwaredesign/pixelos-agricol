"""Découverte automatique de capteurs IoT : Wi-Fi, Bluetooth/BLE, RS485."""

import os
import re
import json
import time
import structlog
import subprocess
from typing import Optional
from pathlib import Path


log = structlog.get_logger()


class DiscoveryProtocol:
    """Protocole de découverte : chaque capteur expose un beacon JSON."""

    # Service UUID personnalisé PixelOS (16-bit)
    BLE_SERVICE_UUID = "0x180F"  # Battery service (fallback)
    PIXELOS_BLE_UUID  = "PIXL"   # 4-byte prefix dans le manufacturer data

    # Wi-Fi AP SSID pattern pour capteurs PixelOS
    WIFI_AP_PATTERN = r"^PIXELOS-(SOL|VANNE|METEO|DEBIT|PIR|POMPE)-([A-Za-z0-9_]+)$"

    @staticmethod
    def parse_wifi_ap(ssid: str) -> Optional[dict]:
        """Parse un SSID de type PIXELOS-TYPE-NOM."""
        m = re.match(r"^PIXELOS-(SOL|VANNE|METEO|DEBIT|PIR|POMPE)-([A-Za-z0-9_]+)$", ssid)
        if not m:
            return None
        return {
            "type": m.group(1).lower(),
            "nom": m.group(2).lower(),
            "communication": "wifi",
        }

    @staticmethod
    def make_wifi_ap(node_type: str, node_name: str) -> str:
        """Génère le SSID pour un capteur PixelOS."""
        return f"PIXELOS-{node_type.upper()}-{node_name.upper()}"

    @staticmethod
    def parse_ble_manufacturer(data: bytes) -> Optional[dict]:
        """Parse les données manufacturer BLE PixelOS."""
        if len(data) < 6:
            return None
        prefix = data[:4].decode("ascii", errors="replace")
        if prefix != "PIXL":
            return None
        node_type = {0: "sol", 1: "vanne", 2: "meteo", 3: "debit", 4: "pir"}.get(
            data[4], "unknown")
        addr = data[5]
        return {
            "type": node_type,
            "addr": addr,
            "communication": "ble",
        }


class WifiScanner:
    """Scan Wi-Fi pour détecter les AP des capteurs PixelOS."""

    def __init__(self, interface: str = "wlan0"):
        self.interface = interface

    def scan(self, timeout: int = 10) -> list[dict]:
        """Scan et retourne la liste des capteurs PixelOS détectés."""
        found = []

        # Méthode 1 : iwlist (Linux)
        try:
            result = subprocess.run(
                ["iwlist", self.interface, "scan"],
                capture_output=True, text=True, timeout=timeout)
            for line in result.stdout.split("\n"):
                line = line.strip()
                if "ESSID" in line:
                    m = re.search(r'ESSID:"([^"]+)"', line)
                    if m:
                        parsed = DiscoveryProtocol.parse_wifi_ap(m.group(1))
                        if parsed:
                            found.append(parsed)
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            log.warning("Scan Wi-Fi timeout")

        # Méthode 2 : nmcli (NetworkManager)
        try:
            result = subprocess.run(
                ["nmcli", "-f", "SSID", "device", "wifi", "list"],
                capture_output=True, text=True, timeout=timeout)
            for line in result.stdout.split("\n"):
                parsed = DiscoveryProtocol.parse_wifi_ap(line.strip())
                if parsed:
                    found.append(parsed)
        except FileNotFoundError:
            pass

        # Méthode 3 : netsh (Windows)
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks"],
                capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace")
            for line in result.stdout.split("\n"):
                if "SSID" in line:
                    m = re.search(r'SSID\s+\d+\s*:\s*(.+)$', line)
                    if m:
                        parsed = DiscoveryProtocol.parse_wifi_ap(m.group(1).strip())
                        if parsed:
                            found.append(parsed)
        except FileNotFoundError:
            pass

        return found


class BLEScanner:
    """Scan Bluetooth/BLE pour les beacons PixelOS."""

    def __init__(self, hci_device: str = "hci0"):
        self.hci_device = hci_device

    def scan(self, timeout: int = 10) -> list[dict]:
        """Scan BLE et retourne les capteurs PixelOS détectés."""
        found = []

        # Méthode 1 : hcitool lescan (Linux)
        try:
            result = subprocess.run(
                ["hcitool", "lescan", "--duplicate"],
                capture_output=True, text=True, timeout=timeout)
            for line in result.stdout.split("\n"):
                parts = line.strip().split()
                if len(parts) >= 2:
                    mac = parts[0]
                    name = " ".join(parts[1:])
                    if "PIXELOS" in name.upper():
                        parsed = DiscoveryProtocol.parse_wifi_ap(name)
                        if parsed:
                            parsed["mac"] = mac
                            parsed["protocol"] = "ble"
                            found.append(parsed)
        except FileNotFoundError:
            pass

        # Méthode 2 : bluetoothctl (Linux)
        try:
            proc = subprocess.Popen(
                ["bluetoothctl", "scan", "on"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
            time.sleep(timeout)
            proc.terminate()
            for line in proc.stdout:
                if "Device" in line:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = " ".join(parts[2:])
                        if "PIXELOS" in name.upper():
                            parsed = DiscoveryProtocol.parse_wifi_ap(name)
                            if parsed:
                                parsed["mac"] = mac
                                parsed["protocol"] = "ble"
                                found.append(parsed)
        except FileNotFoundError:
            pass

        # Méthode 3 : bleak (Python, cross-platform)
        try:
            import asyncio
            from bleak import BleakScanner

            async def _scan():
                devices = await BleakScanner.discover(timeout=timeout)
                for d in devices:
                    if d.name and "PIXELOS" in d.name.upper():
                        parsed = DiscoveryProtocol.parse_wifi_ap(d.name)
                        if parsed:
                            parsed["mac"] = d.address
                            parsed["protocol"] = "ble"
                            parsed["rssi"] = d.rssi
                            found.append(parsed)
                    # Manufacturer data
                    if d.metadata and "manufacturer_data" in d.metadata:
                        for mfg_id, data in d.metadata["manufacturer_data"].items():
                            parsed = DiscoveryProtocol.parse_ble_manufacturer(data)
                            if parsed:
                                parsed["mac"] = d.address
                                parsed["rssi"] = d.rssi
                                found.append(parsed)

            asyncio.run(_scan())
        except ImportError:
            pass
        except Exception as e:
            log.warning("Erreur scan BLE (bleak)", error=str(e))

        return found


class RS485Scanner:
    """Scan du bus RS485 pour découvrir les nœuds Modbus."""

    def __init__(self, port: str = "/dev/ttyUSB0"):
        self.port = port

    def scan(self, timeout: int = 30) -> list[dict]:
        """Énumère les adresses Modbus 1-247 et retourne les réponses."""
        found = []
        try:
            import serial
            import minimalmodbus
        except ImportError:
            log.warning("minimalmodbus non installé, scan RS485 impossible")
            return found

        try:
            for addr in range(1, 248):
                try:
                    instrument = minimalmodbus.Instrument(self.port, addr)
                    instrument.serial.baudrate = 9600
                    instrument.serial.bytesize = 8
                    instrument.serial.parity = serial.PARITY_EVEN
                    instrument.serial.stopbits = 1
                    instrument.serial.timeout = 0.2

                    # Lecture registre 0 (humidité/identifiant)
                    regs = instrument.read_registers(0, 2)
                    found.append({
                        "addr": addr,
                        "reg0": regs[0] if len(regs) > 0 else 0,
                        "reg1": regs[1] if len(regs) > 1 else 0,
                        "communication": "rs485",
                        "protocol": "modbus_rtu",
                    })
                    log.info("Nœud RS485 détecté", addr=addr, regs=regs)

                except Exception:
                    continue

        except Exception as e:
            log.error("Erreur scan RS485", error=str(e))

        return found


class AggregateScanner:
    """Orchestre tous les scans et fusionne les résultats."""

    def __init__(self):
        self.wifi = WifiScanner()
        self.ble = BLEScanner()
        self.rs485 = RS485Scanner()

    def scan_all(self, timeout: int = 30) -> dict:
        """Lance tous les scans en parallèle et fusionne."""
        from concurrent.futures import ThreadPoolExecutor

        results = {"wifi": [], "ble": [], "rs485": [], "total": []}
        seen = set()

        with ThreadPoolExecutor(max_workers=3) as ex:
            f_wifi = ex.submit(self.wifi.scan, timeout // 3)
            f_ble = ex.submit(self.ble.scan, timeout // 3)
            f_rs485 = ex.submit(self.rs485.scan, timeout // 3)

            results["wifi"] = f_wifi.result(timeout=timeout)
            results["ble"] = f_ble.result(timeout=timeout)
            results["rs485"] = f_rs485.result(timeout=timeout)

        # Fusion + déduplication
        for src, devices in results.items():
            if src == "total":
                continue
            for d in devices:
                key = str(d.get("addr", d.get("mac", d.get("nom", ""))))
                if key not in seen:
                    seen.add(key)
                    d["source"] = src
                    results["total"].append(d)

        return results
