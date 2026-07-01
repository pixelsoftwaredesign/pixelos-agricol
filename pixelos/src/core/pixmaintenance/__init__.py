"""
PixMaintenanceBot — Robot de maintenance autonome.

Diagnostique les pannes, applique des patchs via PixRobotCoder,
et émet des certificats de validation (.sig) pour déverrouiller
le robot client.
"""

import os
import time
import json
import hashlib
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable


CERT_DIR = "/etc/pix_state"


@dataclass
class MaintenanceCert:
    target_robot_id: str
    maintenance_id: str
    timestamp: str
    status: str
    checksum: str
    signature: str

    def to_dict(self) -> dict:
        return {
            "target_robot_id": self.target_robot_id,
            "maintenance_id": self.maintenance_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "checksum": self.checksum[:20] + "...",
            "signature": self.signature[:20] + "...",
        }


@dataclass
class RepairOrder:
    node_id: str
    issue_type: str
    priority: float
    description: str
    created_at: float
    status: str = "PENDING"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "issue_type": self.issue_type,
            "priority": self.priority,
            "description": self.description,
            "created_at": self.created_at,
            "status": self.status,
        }


class PixMaintenanceBot:
    """Agent de maintenance autonome.

    Reçoit des ordres de réparation, applique des patchs via
    PixRobotCoder, valide en sandbox, et émet un certificat .sig.
    """

    def __init__(self, bot_id: str = "MAINT_BOT_01"):
        self._bot_id = bot_id
        self._repair_queue: list[RepairOrder] = []
        self._certificates: list[MaintenanceCert] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._robot_coder = None

        self.on_repair_started: Optional[Callable] = None
        self.on_repair_completed: Optional[Callable] = None
        self.on_cert_issued: Optional[Callable] = None

    def set_robot_coder(self, coder):
        self._robot_coder = coder

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def enqueue_repair(self, order: RepairOrder):
        with self._lock:
            self._repair_queue.append(order)
            self._repair_queue.sort(key=lambda o: o.priority, reverse=True)

    def get_queue(self) -> list[RepairOrder]:
        with self._lock:
            return list(self._repair_queue)

    def _process_loop(self):
        while self._running:
            order = None
            with self._lock:
                for o in self._repair_queue:
                    if o.status == "PENDING":
                        order = o
                        break

            if order:
                self._execute_repair(order)
            else:
                time.sleep(1.0)

    def _execute_repair(self, order: RepairOrder):
        with self._lock:
            order.status = "IN_PROGRESS"
        if self.on_repair_started:
            self.on_repair_started(order)

        if self._robot_coder:
            patch = self._robot_coder.analyze_issue(
                node_id=order.node_id,
                error_logs=[order.description],
                metrics={"priority": order.priority},
            )

            result = self._robot_coder.test_in_sandbox(patch)

            if result.success:
                cert = self._issue_certificate(order.node_id, patch.patch_hash)
                with self._lock:
                    order.status = "COMPLETED"
                if self.on_repair_completed:
                    self.on_repair_completed(order)
                if self.on_cert_issued:
                    self.on_cert_issued(cert)
            else:
                with self._lock:
                    order.status = "FAILED"
                if self.on_repair_completed:
                    self.on_repair_completed(order)
        else:
            with self._lock:
                order.status = "FAILED"
            if self.on_repair_completed:
                self.on_repair_completed(order)

    def _issue_certificate(self, target_id: str, checksum: str) -> MaintenanceCert:
        maint_id = f"PATCH_{int(time.time())}_{target_id}"
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        cert_data = {
            "target_robot_id": target_id,
            "maintenance_id": maint_id,
            "timestamp": ts,
            "status": "VALIDATED",
            "checksum": checksum,
        }

        signature_input = json.dumps(cert_data, sort_keys=True) + self._bot_id
        signature = hashlib.sha512(signature_input.encode()).hexdigest()

        cert = MaintenanceCert(
            target_robot_id=target_id,
            maintenance_id=maint_id,
            timestamp=ts,
            status="VALIDATED",
            checksum=checksum,
            signature=signature,
        )

        with self._lock:
            self._certificates.append(cert)

        os.makedirs(CERT_DIR, exist_ok=True)
        cert_path = os.path.join(CERT_DIR, f"{target_id}.sig")
        with open(cert_path, "w") as f:
            json.dump(cert_data | {"signature": signature}, f, indent=2)

        return cert

    def verify_certificate(self, target_id: str) -> bool:
        cert_path = os.path.join(CERT_DIR, f"{target_id}.sig")
        if not os.path.exists(cert_path):
            return False
        try:
            with open(cert_path) as f:
                data = json.load(f)
            return data.get("status") == "VALIDATED"
        except (json.JSONDecodeError, KeyError):
            return False

    def get_certificates(self) -> list[MaintenanceCert]:
        with self._lock:
            return list(self._certificates)

    def get_repair_stats(self) -> dict:
        with self._lock:
            total = len(self._repair_queue)
            completed = sum(1 for o in self._repair_queue if o.status == "COMPLETED")
            failed = sum(1 for o in self._repair_queue if o.status == "FAILED")
            pending = sum(1 for o in self._repair_queue if o.status == "PENDING")
            in_progress = sum(1 for o in self._repair_queue if o.status == "IN_PROGRESS")
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "in_progress": in_progress,
                "certificates_issued": len(self._certificates),
            }

    def status(self) -> dict:
        return {
            "bot_id": self._bot_id,
            "running": self._running,
            "queue_size": len(self._repair_queue),
            **self.get_repair_stats(),
        }

    def close(self):
        self.stop()


__all__ = [
    "PixMaintenanceBot", "MaintenanceCert", "RepairOrder",
]
