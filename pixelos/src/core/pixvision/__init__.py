"""
PixVision — Détection d'objets connectés et non connectés.

Modules:
  - scanner: Réseau IoT (ARP, ports, OUI)
  - detector: Vision IA (YOLO, SafetyReactor, EnvironmentMap)
  - registry: Fusion IDs physique + réseau (SQLite, PixIPC, Digital Twin)
  - oui_db: Base OUI IEEE fabricants agricoles
"""

from .scanner import NetworkScanner, NetworkDevice, scanner
from .detector import (
    DetectionResult, SimulatedInference, KalmanFilter2D,
    SafetyReactor, EnvironmentMap, PixDetector,
    detector, env_map,
)
from .registry import ObjectRegistry, registry
from .oui_db import lookup_oui, is_iot_likely

__all__ = [
    "NetworkScanner", "NetworkDevice", "scanner",
    "DetectionResult", "SimulatedInference", "KalmanFilter2D",
    "SafetyReactor", "EnvironmentMap", "PixDetector",
    "detector", "env_map",
    "ObjectRegistry", "registry",
    "lookup_oui", "is_iot_likely",
]
