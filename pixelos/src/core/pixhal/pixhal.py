#!/usr/bin/env python3
"""
PixHAL — Hardware Abstraction Layer PixelOS.

Détecte automatiquement les capteurs et actionneurs agricoles,
les expose via une API standardisée. Compatible Raspberry Pi,
serveurs x86, matériel embarqué OpenBSD.
"""

import os
import json
import glob
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from math import sqrt


HAL_DIR = "/var/db/pixelos/pixhal"
DEVICES_FILE = "detected_devices.json"

I2C_DEVICES = "/dev/i2c-*"
GPIO_BASE = "/sys/class/gpio"
USB_DEVICES = "/dev/ttyUSB*"
VIDEO_DEVICES = "/dev/video*"

SENSOR_DB = {
    "DHT22":  {"type": "temp_humidity", "protocol": "gpio", "pin": 4},
    "BME280": {"type": "temp_humidity_pressure", "protocol": "i2c", "addr": "0x76"},
    "DS18B20": {"type": "temperature", "protocol": "1wire"},
    "BH1750": {"type": "light", "protocol": "i2c", "addr": "0x23"},
    "HC-SR04": {"type": "ultrasonic", "protocol": "gpio", "trig": 23, "echo": 24},
    "MQ-135": {"type": "air_quality", "protocol": "adc"},
    "YL-69": {"type": "soil_moisture", "protocol": "adc"},
    "Camera": {"type": "camera", "protocol": "usb"},
}

ACTUATOR_DB = {
    "Relay": {"type": "switch", "protocol": "gpio"},
    "Servo": {"type": "motor", "protocol": "gpio", "pwm": True},
    "Valve": {"type": "valve", "protocol": "gpio"},
    "Pump": {"type": "pump", "protocol": "gpio"},
    "Fan": {"type": "fan", "protocol": "gpio"},
}

# Profils de drones supportés (MAVLink / Pixhawk / simulation)
DRONE_PROFILES = {
    "pixhawk": {"protocol": "mavlink", "baud": 115200, "device": "/dev/ttyACM0"},
    "simulated": {"protocol": "simulated", "baud": 0, "device": ""},
}


class PixHAL:
    def __init__(self):
        self._ensure_dirs()
        self._load_devices()
        self.sensors = {}
        self.actuators = {}

    def _ensure_dirs(self):
        Path(HAL_DIR).mkdir(parents=True, exist_ok=True)

    def _path(self, name):
        return str(Path(HAL_DIR) / name)

    def _load_devices(self):
        path = self._path(DEVICES_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                    self.sensors = data.get("sensors", {})
                    self.actuators = data.get("actuators", {})
                return
            except Exception:
                pass
        self.sensors = {}
        self.actuators = {}

    def _save_devices(self):
        with open(self._path(DEVICES_FILE), "w") as f:
            json.dump({"sensors": self.sensors, "actuators": self.actuators}, f, indent=2)

    # ── Detection ─────────────────────────────────────────

    def detect_all(self) -> dict:
        results = {"sensors": {}, "actuators": {}}

        # I2C scan
        i2c = self._scan_i2c()
        results["sensors"].update(i2c)

        # GPIO check
        gpio = self._scan_gpio()
        results["sensors"].update(gpio)

        # USB serial
        usb = self._scan_usb()
        results["sensors"].update(usb)

        # Video (cameras)
        video = self._scan_video()
        results["sensors"].update(video)

        # 1-Wire (DS18B20)
        onewire = self._scan_onewire()
        results["sensors"].update(onewire)

        # System info
        sysinfo = self._detect_system()
        results["system"] = sysinfo

        self.sensors.update(results["sensors"])
        self.actuators.update(results["actuators"])
        self._save_devices()
        results["detected_at"] = datetime.now().isoformat()
        return results

    def _scan_i2c(self) -> dict:
        found = {}
        for dev in glob.glob(I2C_DEVICES):
            try:
                bus = dev.split("-")[-1]
                r = subprocess.run(["i2cdetect", "-y", bus],
                                   capture_output=True, text=True, timeout=5)
                for line in r.stdout.split("\n")[1:]:
                    if not line.strip():
                        continue
                    parts = line.split()
                    addr = parts[0].rstrip(":")
                    for i, cell in enumerate(parts[1:]):
                        if cell not in ("--", "UU"):
                            full_addr = f"0x{int(addr, 16) + i:02x}"
                            detected = self._identify_i2c(full_addr)
                            if detected:
                                dev_id = f"i2c_{bus}_{full_addr}"
                                found[dev_id] = {
                                    "bus": bus, "addr": full_addr,
                                    "model": detected, **SENSOR_DB.get(detected, {}),
                                    "path": dev,
                                }
            except Exception:
                pass
        return found

    def _identify_i2c(self, addr: str) -> Optional[str]:
        lookup = {"0x76": "BME280", "0x77": "BME280",
                  "0x23": "BH1750", "0x5c": "BH1750",
                  "0x27": "LCD", "0x3f": "LCD"}
        return lookup.get(addr)

    def _scan_gpio(self) -> dict:
        found = {}
        if os.path.exists(GPIO_BASE):
            for gpio in glob.glob(f"{GPIO_BASE}/gpio*"):
                num = gpio.split("gpio")[-1]
                direction = Path(f"{gpio}/direction").read_text().strip() if Path(f"{gpio}/direction").exists() else "unknown"
                dev_id = f"gpio_{num}"
                found[dev_id] = {"pin": int(num), "direction": direction,
                                 "protocol": "gpio", "path": gpio}
        return found

    def _scan_usb(self) -> dict:
        found = {}
        for usb in glob.glob(USB_DEVICES):
            dev_id = f"usb_{Path(usb).name}"
            found[dev_id] = {"path": usb, "protocol": "usb_serial",
                             "type": "serial_sensor", "model": "USB-Serial"}
        return found

    def _scan_video(self) -> dict:
        found = {}
        for vid in glob.glob(VIDEO_DEVICES):
            dev_id = f"camera_{Path(vid).name}"
            found[dev_id] = {"path": vid, "protocol": "usb",
                             "type": "camera", "model": "Camera"}
        return found

    def _scan_onewire(self) -> dict:
        found = {}
        w1_base = "/sys/bus/w1/devices"
        if os.path.exists(w1_base):
            for dev in glob.glob(f"{w1_base}/28-*"):
                dev_id = f"1wire_{Path(dev).name}"
                found[dev_id] = {"path": dev, "protocol": "1wire",
                                 "type": "temperature", "model": "DS18B20"}
        return found

    def _detect_system(self) -> dict:
        import platform as _platform
        info = {
            "hostname": _platform.node(),
            "os": _platform.system(),
            "kernel": _platform.release() if hasattr(_platform, 'release') else "unknown",
            "arch": _platform.machine(),
        }
        try:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "Model" in line:
                            info["board"] = line.split(":")[-1].strip()
                            break
        except Exception:
            pass
        try:
            r = subprocess.run(["sysctl", "-n", "hw.model"],
                               capture_output=True, text=True, timeout=3)
            if r.stdout.strip():
                info["board"] = r.stdout.strip()
        except Exception:
            pass
        return info

    # ── Access ────────────────────────────────────────────

    def read_sensor(self, sensor_id: str) -> Optional[dict]:
        sensor = self.sensors.get(sensor_id)
        if not sensor:
            return None

        protocol = sensor.get("protocol", "")
        try:
            if protocol == "1wire" and sensor.get("model") == "DS18B20":
                w1_path = f"{sensor['path']}/temperature"
                if os.path.exists(w1_path):
                    raw = Path(w1_path).read_text().strip()
                    temp = int(raw) / 1000
                    return {"sensor_id": sensor_id, "temperature": temp, "unit": "°C"}

            elif protocol == "i2c" and sensor.get("model") == "BME280":
                r = subprocess.run(["python3", "-c", f"""
import smbus; bus = smbus.SMBus({sensor['bus']})
addr = int('{sensor['addr']}', 16)
data = bus.read_i2c_block_data(addr, 0xF7, 8)
print(data)"""], capture_output=True, text=True, timeout=5)
                return {"sensor_id": sensor_id, "raw": r.stdout.strip()}

            return {"sensor_id": sensor_id, "status": "simulated",
                    "temperature": 25.0, "humidity": 60.0}
        except Exception as e:
            return {"sensor_id": sensor_id, "error": str(e)}

    def write_actuator(self, actuator_id: str, state: int) -> dict:
        actuator = self.actuators.get(actuator_id)
        if not actuator:
            return {"status": "error", "reason": "not found"}
        try:
            if actuator.get("protocol") == "gpio":
                pin = actuator.get("pin", 0)
                gpio_path = f"{GPIO_BASE}/gpio{pin}"
                if not os.path.exists(gpio_path):
                    Path(f"{GPIO_BASE}/export").write_text(str(pin))
                Path(f"{gpio_path}/direction").write_text("out")
                Path(f"{gpio_path}/value").write_text(str(state))
                return {"status": "ok", "actuator_id": actuator_id, "pin": pin, "state": state}
            return {"status": "simulated", "actuator_id": actuator_id, "state": state}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    # ── Drone / Vol ───────────────────────────────────────

    def detect_drone(self) -> dict:
        """Détecte un contrôleur de vol (Pixhawk / simulation)."""
        for name, profile in DRONE_PROFILES.items():
            if profile["protocol"] == "mavlink":
                dev = profile["device"]
                if os.path.exists(dev):
                    return {"status": "ok", "profile": name, **profile}
            if name == "simulated":
                return {"status": "simulated", "profile": "simulated"}
        return {"status": "not_found"}

    def flight_arm(self) -> dict:
        return {"status": "simulated", "command": "arm", "profile": "simulated"}

    def flight_disarm(self) -> dict:
        return {"status": "simulated", "command": "disarm", "profile": "simulated"}

    def flight_takeoff(self, altitude: float) -> dict:
        if altitude < 0.5 or altitude > 120:
            return {"status": "error", "reason": "altitude hors limites (0.5-120m)"}
        return {
            "status": "simulated",
            "command": "takeoff",
            "altitude": altitude,
            "profile": "simulated",
        }

    def flight_land(self) -> dict:
        return {"status": "simulated", "command": "land", "profile": "simulated"}

    def flight_goto(self, lat: float, lon: float, alt: float = None) -> dict:
        payload = {"lat": lat, "lon": lon}
        if alt is not None:
            payload["altitude"] = alt
        return {
            "status": "simulated",
            "command": "goto",
            **payload,
            "profile": "simulated",
        }

    def flight_rc_override(self, channels: dict) -> dict:
        return {
            "status": "simulated",
            "command": "rc_override",
            "channels": channels,
            "profile": "simulated",
        }

    # ── Motor control (robots terrestres) ─────────────────

    def motor_speed(self, motor_id: str, speed: int) -> dict:
        """Contrôle vitesse d'un moteur (PWM 0-255)."""
        speed = max(0, min(255, speed))
        actuator = self.actuators.get(motor_id)
        if actuator and actuator.get("protocol") == "gpio":
            pin = actuator.get("pin", 0)
            try:
                gpio_path = f"{GPIO_BASE}/gpio{pin}"
                if not os.path.exists(gpio_path):
                    Path(f"{GPIO_BASE}/export").write_text(str(pin))
                Path(f"{gpio_path}/direction").write_text("out")
                Path(f"{gpio_path}/value").write_text(str(1 if speed > 0 else 0))
                return {"status": "ok", "motor_id": motor_id, "speed": speed}
            except Exception as e:
                return {"status": "error", "reason": str(e)}
        return {"status": "simulated", "motor_id": motor_id, "speed": speed}

    # ── List ──────────────────────────────────────────────

    def list_devices(self) -> dict:
        return {"sensors": self.sensors, "actuators": self.actuators}

    def get_system_info(self) -> dict:
        return self._detect_system()

    # ── Stats ─────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "sensors_count": len(self.sensors),
            "actuators_count": len(self.actuators),
            "sensor_types": list(set(s.get("type", "unknown") for s in self.sensors.values())),
            "protocols": list(set(s.get("protocol", "unknown") for s in self.sensors.values())),
            "system": self._detect_system(),
        }
