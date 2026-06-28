#!/usr/bin/env python3
"""
PixelOS Agent - Daemon de gestion et monitoring déployé sur chaque machine.
Collecte les métriques, exécute les commandes, et maintient le heartbeat.

Installation:
  - Sur OpenBSD: rcctl enable pixelos_agent
  - Sur Raspberry Pi: systemctl enable pixelos-agent
"""

import os
import sys
import json
import time
import signal
import structlog
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import PixelOSConfig
from core.mqtt import PixelOSMQTT


log = structlog.get_logger()


class Agent:
    """Agent PixelOS déployé sur chaque nœud du système."""

    def __init__(self, node_id: str, role: str):
        self.node_id = node_id
        self.role = role
        self.config = PixelOSConfig()
        self.mqtt = PixelOSMQTT(
            broker=self.config.get("mqtt.broker", "localhost"),
            port=self.config.get("mqtt.port", 1883),
            client_id=f"pixelos-agent-{node_id}",
        )
        self.running = True
        self._interval = self.config.get("monitoring.poll_interval", 10)
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

    def _stop(self, *args):
        self.running = False

    def start(self) -> None:
        log.info("Agent démarré", node=self.node_id, role=self.role)

        # Démarrage automatique des services au boot
        if self.node_id == "pixelos-server" or self.role == "server":
            self._startup_services()

        self.mqtt.connect()

        # Souscription aux commandes
        self.mqtt.subscribe(f"pixelos/agent/{self.node_id}/cmd/#",
                            self._on_command)
        self.mqtt.subscribe("pixelos/agent/all/cmd/#", self._on_command)

        while self.running:
            try:
                # Collecte métriques
                metrics = self._collect_metrics()

                # Heartbeat
                self.mqtt.publish(f"pixelos/agent/{self.node_id}/heartbeat", {
                    "node": self.node_id,
                    "role": self.role,
                    "ts": datetime.now().isoformat(),
                    "metrics": metrics,
                })

                # Vérification alertes locales
                self._check_alerts(metrics)

                time.sleep(self._interval)

            except Exception as e:
                log.error("Erreur agent", error=str(e))
                time.sleep(5)

    def _collect_metrics(self) -> dict[str, Any]:
        metrics = {
            "cpu": self._get_cpu(),
            "memory": self._get_memory(),
            "disk": self._get_disk(),
            "uptime": self._get_uptime(),
            "processes": self._get_processes(),
        }

        # Métriques spécifiques au rôle
        if self.role == "openbsd":
            metrics.update(self._get_openbsd_metrics())
        elif self.role == "rpi":
            metrics.update(self._get_rpi_metrics())
        elif self.role == "gateway":
            metrics.update(self._get_gateway_metrics())

        return metrics

    def _get_cpu(self) -> dict:
        try:
            import psutil
            return {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
                "load": os.getloadavg() if hasattr(os, "getloadavg") else [],
            }
        except:
            return {"percent": 0}

    def _get_memory(self) -> dict:
        try:
            import psutil
            m = psutil.virtual_memory()
            return {"total": m.total, "available": m.available,
                    "percent": m.percent}
        except:
            return {"percent": 0}

    def _get_disk(self) -> dict:
        try:
            import psutil
            d = psutil.disk_usage("/")
            return {"total": d.total, "used": d.used, "free": d.free,
                    "percent": d.percent}
        except:
            return {"percent": 0}

    def _get_uptime(self) -> float:
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except:
            return 0

    def _get_processes(self) -> list:
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(p.info)
                except:
                    pass
            return sorted(procs, key=lambda x: x.get("cpu_percent", 0),
                          reverse=True)[:20]
        except:
            return []

    def _get_openbsd_metrics(self) -> dict:
        metrics = {}
        try:
            # Sensor temperature
            result = subprocess.run(
                ["sysctl", "hw.sensors"],
                capture_output=True, text=True, timeout=5)
            metrics["sensors"] = result.stdout.strip()
        except:
            pass

        try:
            # PF state count
            result = subprocess.run(
                ["pfctl", "-s", "info"],
                capture_output=True, text=True, timeout=5)
            for line in result.stdout.split("\n"):
                if "entries" in line:
                    metrics["pf_states"] = line.strip()
        except:
            pass

        try:
            # Watchdog status
            result = subprocess.run(
                ["sysctl", "-n", "hw.watchdog"],
                capture_output=True, text=True, timeout=5)
            metrics["watchdog"] = result.stdout.strip()
        except:
            pass

        return metrics

    def _get_rpi_metrics(self) -> dict:
        metrics = {}
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True, text=True, timeout=5)
            metrics["cpu_temp"] = result.stdout.strip()
        except:
            pass
        return metrics

    def _get_gateway_metrics(self) -> dict:
        metrics = {}
        try:
            # Serial gateway health
            result = subprocess.run(
                ["pgrep", "-a", "serial_gateway"],
                capture_output=True, text=True, timeout=5)
            metrics["gateway_running"] = bool(result.stdout.strip())
        except:
            metrics["gateway_running"] = False
        return metrics

    def _check_alerts(self, metrics: dict) -> None:
        """Vérifie les conditions d'alerte locales."""
        if metrics.get("cpu", {}).get("percent", 0) > 90:
            self.mqtt.publish(f"pixelos/agent/{self.node_id}/alert", {
                "type": "cpu_high",
                "value": metrics["cpu"]["percent"],
                "severity": "warning",
            })

        disk = metrics.get("disk", {}).get("percent", 0)
        if disk > 90:
            self.mqtt.publish(f"pixelos/agent/{self.node_id}/alert", {
                "type": "disk_full",
                "value": disk,
                "severity": "critical",
            })

    def _on_command(self, topic: str, payload: dict) -> None:
        """Exécute une commande reçue via MQTT."""
        cmd = payload.get("cmd")
        log.info("Commande reçue", topic=topic, cmd=cmd)

        if cmd == "restart":
            log.warning("Redémarrage demandé")
            subprocess.run(["shutdown", "-r", "now"])
        elif cmd == "update":
            self._self_update()
        elif cmd == "ping":
            self.mqtt.publish(f"pixelos/agent/{self.node_id}/pong", {
                "ts": datetime.now().isoformat(),
            })
        elif cmd == "exec":
            script = payload.get("script", "")
            try:
                result = subprocess.run(
                    script, shell=True, capture_output=True,
                    text=True, timeout=30)
                self.mqtt.publish(
                    f"pixelos/agent/{self.node_id}/exec_result", {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode,
                    })
            except Exception as e:
                self.mqtt.publish(
                    f"pixelos/agent/{self.node_id}/exec_result", {
                        "error": str(e),
                    })

    def _startup_services(self) -> None:
        """Démarre tous les services PixelOS au boot."""
        try:
            from core.services import ServiceManager
            svc = ServiceManager()
            log.info("Démarrage automatique des services PixelOS...")
            result = svc.start()
            status = svc.health()
            log.info("Services démarrés",
                     running=status["running"],
                     total=status["total"])
            # Envoyer heartbeat de boot
            if hasattr(self, "mqtt") and self.mqtt:
                self.mqtt.publish("pixelos/server/boot", {
                    "node": self.node_id,
                    "services": status,
                    "ts": datetime.now().isoformat(),
                })
        except ImportError:
            log.warning("ServiceManager non disponible")
        except Exception as e:
            log.error("Échec démarrage services", error=str(e))

    def _self_update(self) -> None:
        """Mise à jour de l'agent lui-même."""
        try:
            subprocess.run(["pip", "install", "--upgrade", "pixelos"],
                           timeout=60)
            log.info("Agent mis à jour, redémarrage...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            log.error("Échec mise à jour agent", error=str(e))


if __name__ == "__main__":
    node_id = os.environ.get("PIXELOS_NODE_ID", os.uname()[1])
    role = os.environ.get("PIXELOS_ROLE", "unknown")

    agent = Agent(node_id, role)
    agent.start()
