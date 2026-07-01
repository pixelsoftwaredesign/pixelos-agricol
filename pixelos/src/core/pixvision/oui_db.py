"""
PixVision OUI Database — IEEE MAC prefix → manufacturer mapping.
Embedded subset focused on agricultural / industrial IoT devices.
Full OUI registry: https://standards.ieee.org/products-programs/regauth/
"""

OUI_DB = {
    # Cisco / networking
    "00:1A:A1": "Cisco Systems",
    "00:1E:13": "Cisco Systems",
    "00:1B:D4": "Cisco Systems",
    "8C:7C:92": "Netgear",
    "D8:5D:E2": "TP-Link Technologies",
    "14:CF:92": "TP-Link Technologies",
    "C0:4A:00": "Ubiquiti Networks",
    "18:E8:29": "Ubiquiti Networks",
    "00:27:22": "Ubiquiti Networks",
    "00:24:A2": "MikroTik",
    "4C:5E:0C": "MikroTik",
    "64:D1:54": "MikroTik",
    # Agricultural sensors
    "00:1E:C0": "Decagon Devices (Meter Group)",
    "00:50:C2": "Meter Group",
    "00:60:37": "Campbell Scientific",
    "4C:5F:70": "Campbell Scientific",
    "00:11:22": "Davis Instruments",
    "00:1E:8C": "Davis Instruments",
    "00:17:61": "Texas Instruments (IoT)",
    "C0:83:0A": "Texas Instruments",
    "00:12:4B": "STMicroelectronics",
    "D0:39:72": "STMicroelectronics",
    # Drone / robotics
    "00:26:7E": "DJI",
    "34:D2:70": "DJI",
    "A0:14:3D": "DJI",
    "00:24:BE": "ArduPilot / 3DRobotics",
    "00:1E:42": "Pixhawk / Holybro",
    "00:0C:BF": "KMel Robotics",
    # Environmental / weather
    "00:1A:5B": "Vaisala",
    "48:2C:A0": "Vaisala",
    "00:09:0D": "Lufft (OTT)",
    "00:14:72": "Gill Instruments",
    # Agricultural machinery
    "00:17:7D": "John Deere",
    "00:1B:E5": "John Deere",
    "00:21:59": "John Deere",
    "00:1D:FD": "AGCO Corporation",
    "00:1F:CE": "CNH Industrial",
    "00:22:6B": "Trimble Navigation",
    "00:24:6C": "Trimble Navigation",
    "00:0F:8F": "Topcon Positioning",
    "00:25:22": "Hexagon / Leica",
    # Irrigation
    "00:0B:7D": "Rain Bird",
    "00:1A:6B": "Hunter Industries",
    "00:08:1B": "Toro Company",
    "00:1E:6C": "Netafim",
    # Solar / energy
    "00:0E:C6": "Enphase Energy",
    "00:1B:0A": "SolarEdge",
    "00:1D:6F": "Fronius International",
    "00:14:BE": "ABB (solar)",
    # Raspberry Pi / SBC
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Foundation",
    "E4:5F:01": "Raspberry Pi Foundation",
    "00:14:2D": "Arduino LLC",
    # LoRa / LPWAN
    "00:80:00": "Semtech (LoRa)",
    "00:24:BA": "Libelium (Waspmote)",
    "00:0B:7B": "MultiTech Systems",
    "00:15:8D": "Dell (Edge Gateway)",
    # BLE / beacons
    "F0:08:D1": "Nordic Semiconductor (nRF)",
    "E0:52:33": "Nordic Semiconductor",
    "60:A4:23": "Silicon Labs",
    "00:1A:7D": "Texas Instruments (BLE)",
    "50:3E:AA": "Dialog Semiconductor",
    # Networking infrastructure
    "00:1C:B3": "Digi International",
    "00:1D:DF": "Advantech",
    "00:0B:5B": "Wago Kontakttechnik",
    "00:1F:C5": "Siemens (IoT)",
    "00:1E:C1": "Bosch Connected Devices",
    "00:15:BC": "Pepperl+Fuchs",
    "00:1B:1B": "Phoenix Contact",
    # Rock / SBC
    "FC:FC:48": "Radxa (Rockchip)",
    "1C:81:54": "FriendlyElec (NanoPi)",
    "00:22:69": "Hardkernel (ODROID)",
    "28:CD:C1": "Espressif (ESP32 BLE)",
    "24:0A:C4": "Espressif (ESP32 WiFi)",
    "24:6F:28": "Espressif (ESP8266)",
    "18:FE:34": "Espressif (ESP32)",
    "EC:FA:BC": "Espressif (ESP32-CAM)",
    "10:52:1C": "Espressif (ESP32-S3)",
    "F4:CF:A2": "Espressif (ESP32-C6)",
    # Rockwell / industrial
    "00:00:BC": "Rockwell Automation",
    "00:0B:DB": "Schneider Electric",
    "00:01:23": "Mitsubishi Electric",
    "00:07:46": "Omron",
}

# Reverse lookup: device type by manufacturer substring
DEVICE_CLASSIFICATION = {
    "John Deere": ("machinerie", 0.95),
    "AGCO": ("machinerie", 0.90),
    "CNH": ("machinerie", 0.90),
    "Trimble": ("gnss", 0.95),
    "Topcon": ("gnss", 0.85),
    "Leica": ("gnss", 0.90),
    "Hexagon": ("gnss", 0.85),
    "Campbell Scientific": ("station_meteo", 0.95),
    "Davis Instruments": ("station_meteo", 0.90),
    "Vaisala": ("station_meteo", 0.95),
    "Lufft": ("station_meteo", 0.85),
    "Gill Instruments": ("anemometre", 0.90),
    "Meter Group": ("capteur_sol", 0.95),
    "Decagon": ("capteur_sol", 0.95),
    "Rain Bird": ("irrigation", 0.90),
    "Hunter Industries": ("irrigation", 0.85),
    "Toro": ("irrigation", 0.85),
    "Netafim": ("irrigation", 0.90),
    "DJI": ("drone", 0.95),
    "ArduPilot": ("drone", 0.85),
    "Pixhawk": ("drone", 0.85),
    "Enphase": ("solaire", 0.90),
    "SolarEdge": ("solaire", 0.95),
    "Fronius": ("solaire", 0.85),
    "ABB": ("solaire", 0.70),
    "Semtech": ("lora", 0.90),
    "Libelium": ("iot_gateway", 0.85),
    "MultiTech": ("iot_gateway", 0.80),
    "Raspberry Pi": ("sbc", 0.90),
    "Arduino": ("microcontroleur", 0.85),
    "Espressif": ("microcontroleur", 0.85),
    "Nordic": ("microcontroleur", 0.80),
    "Silicon Labs": ("microcontroleur", 0.80),
    "Dialog": ("microcontroleur", 0.75),
    "Texas Instruments": ("microcontroleur", 0.70),
    "STMicro": ("microcontroleur", 0.70),
    "Siemens": ("automate", 0.90),
    "Rockwell": ("automate", 0.90),
    "Schneider": ("automate", 0.85),
    "Mitsubishi": ("automate", 0.85),
    "Omron": ("automate", 0.85),
    "Wago": ("automate", 0.80),
    "Pepperl+Fuchs": ("capteur_industriel", 0.85),
    "Phoenix Contact": ("capteur_industriel", 0.80),
    "Bosch": ("capteur_industriel", 0.70),
    "Advantech": ("iot_gateway", 0.80),
    "Digi": ("iot_gateway", 0.85),
    "Dell": ("serveur_edge", 0.80),
    "Radxa": ("sbc", 0.80),
    "FriendlyElec": ("sbc", 0.80),
    "Hardkernel": ("sbc", 0.80),
    "Ubiquiti": ("reseau", 0.85),
    "MikroTik": ("reseau", 0.85),
    "Cisco": ("reseau", 0.90),
    "Netgear": ("reseau", 0.70),
    "TP-Link": ("reseau", 0.70),
}


def lookup_oui(mac: str) -> dict:
    """Look up manufacturer by MAC address.
    
    Returns dict with manufacturer, device_type, and confidence, or unknown.
    """
    mac_clean = mac.upper().replace("-", ":").replace(".", ":")
    parts = mac_clean.split(":")
    
    if len(parts) < 3:
        return {
            "manufacturer": "Inconnu",
            "device_type": "inconnu",
            "confidence": 0.0
        }
    
    prefix = f"{parts[0]}:{parts[1]}:{parts[2]}"
    if prefix in OUI_DB:
        mfr = OUI_DB[prefix]
        for key, (dtype, conf) in DEVICE_CLASSIFICATION.items():
            if key in mfr:
                return {
                    "manufacturer": mfr,
                    "device_type": dtype,
                    "confidence": conf
                }
        return {
            "manufacturer": mfr,
            "device_type": "equipement_reseau",
            "confidence": 0.5
        }
    
    # Try 1-octet match for broadcast/OUI-36
    return {
        "manufacturer": "Inconnu",
        "device_type": "inconnu",
        "confidence": 0.0
    }


def is_iot_likely(mac: str, open_ports: list = None) -> bool:
    """Heuristic: is this device likely an IoT/sensor vs general compute?"""
    info = lookup_oui(mac)
    if info["confidence"] >= 0.8:
        return True
    if open_ports:
        iot_ports = {1883, 8883, 5683, 5684, 502, 2404, 2455,
                     1024, 5000, 8080, 80, 443, 22}
        match = iot_ports & set(open_ports)
        if match:
            return True
    return False


__all__ = [
    "OUI_DB", "DEVICE_CLASSIFICATION",
    "lookup_oui", "is_iot_likely",
]
