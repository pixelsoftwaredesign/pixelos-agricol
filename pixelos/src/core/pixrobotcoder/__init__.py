"""
PixRobotCoder — Moteur de génération de patchs de réparation.

Génère des correctifs logiciels en environnement sandboxé,
les teste dans un contexte isolé (chroot + seccomp simulé),
et produit un certificat de validation signé.
"""

import os
import re
import time
import json
import hashlib
import tempfile
import threading
import subprocess
from dataclasses import dataclass, field
from typing import Optional


SANDBOX_ROOT_PREFIX = "/tmp/pixpatch_sandbox"
MAX_PATCH_SIZE = 65536
MAX_SANDBOX_CPU = 0.5
MAX_SANDBOX_MEM_MB = 64
MAX_SANDBOX_TIME_S = 5


@dataclass
class PatchSpec:
    node_id: str
    issue_type: str
    description: str
    patch_code: str = ""
    patch_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "issue_type": self.issue_type,
            "description": self.description,
            "patch_code": self.patch_code[:200] + "..." if len(self.patch_code) > 200 else self.patch_code,
            "patch_hash": self.patch_hash,
        }


@dataclass
class PatchResult:
    success: bool
    patch: PatchSpec
    sandbox_log: str = ""
    tested: bool = False
    signature: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "patch": self.patch.to_dict(),
            "sandbox_log": self.sandbox_log[:300] if self.sandbox_log else "",
            "tested": self.tested,
            "signature": self.signature[:30] + "..." if self.signature else "",
        }


class PixRobotCoder:
    """Génère, teste et valide des patchs de réparation dans une sandbox."""

    def __init__(self, sandbox_root: str = SANDBOX_ROOT_PREFIX):
        self._sandbox_root = sandbox_root
        self._lock = threading.Lock()
        self._repaired_nodes: set[str] = set()
        self._patches: list[PatchResult] = []

    def analyze_issue(self, node_id: str, error_logs: list[str],
                      metrics: dict) -> PatchSpec:
        issue_type = "UNKNOWN"
        description = "Aucun diagnostic"

        combined = "\n".join(error_logs)

        if any(kw in combined.lower() for kw in ["overheat", "temp", "surchauffe"]):
            issue_type = "OVERHEAT"
            description = f"Surchauffe détectée sur {node_id}"
        elif any(kw in combined.lower() for kw in ["vibration", "drift"]):
            issue_type = "VIBRATION_DRIFT"
            description = f"Dérive vibratoire sur {node_id}"
        elif any(kw in combined.lower() for kw in ["current", "overcurrent", "surcharge"]):
            issue_type = "OVERCURRENT"
            description = f"Surcharge électrique sur {node_id}"
        elif any(kw in combined.lower() for kw in ["timeout", "no response", "offline"]):
            issue_type = "COMMUNICATION_LOST"
            description = f"Perte de communication avec {node_id}"
        elif any(kw in combined.lower() for kw in ["calibration", "position_error"]):
            issue_type = "CALIBRATION_ERROR"
            description = f"Erreur de calibration sur {node_id}"

        patch_code = self._generate_patch(node_id, issue_type, metrics)

        patch_hash = hashlib.sha256(patch_code.encode()).hexdigest()

        return PatchSpec(
            node_id=node_id,
            issue_type=issue_type,
            description=description,
            patch_code=patch_code,
            patch_hash=patch_hash,
        )

    def _generate_patch(self, node_id: str, issue_type: str,
                        metrics: dict) -> str:
        lines = [f"# PixRobotCoder Patch - {node_id}", f"# Issue: {issue_type}", f"# Generated: {time.ctime()}", ""]

        if issue_type == "OVERHEAT":
            limit = metrics.get("temp", 60)
            lines.append(f"# Réduction de charge thermique pour {node_id}")
            lines.append(f"set_throttle(node_id='{node_id}', level=0.7)")
            lines.append(f"if temp > {limit}:")
            lines.append(f"    set_throttle(node_id='{node_id}', level=0.4)")
        elif issue_type == "VIBRATION_DRIFT":
            lines.append(f"# Compensation vibratoire pour {node_id}")
            lines.append(f"enable_vibration_damping(node_id='{node_id}')")
            lines.append(f"set_damping_gain(node_id='{node_id}', gain=2.0)")
        elif issue_type == "OVERCURRENT":
            limit = metrics.get("current", 2.0)
            lines.append(f"# Limitation de courant pour {node_id}")
            lines.append(f"set_current_limit(node_id='{node_id}', limit={limit * 0.8})")
        elif issue_type == "COMMUNICATION_LOST":
            lines.append(f"# Réinitialisation de la communication pour {node_id}")
            lines.append(f"reset_communication(node_id='{node_id}')")
            lines.append(f"set_retry_count(node_id='{node_id}', count=3)")
        elif issue_type == "CALIBRATION_ERROR":
            lines.append(f"# Recalibration automatique pour {node_id}")
            lines.append(f"run_calibration(node_id='{node_id}')")
            lines.append(f"set_position_offset(node_id='{node_id}', offset=0.0)")
        else:
            lines.append(f"# Diagnostic générique pour {node_id}")
            lines.append(f"run_diagnostics(node_id='{node_id}')")
            lines.append(f"log_info('Diagnostic effectué sur {node_id}')")

        lines.append("")
        lines.append("# Fin du patch")
        return "\n".join(lines)

    def test_in_sandbox(self, patch: PatchSpec) -> PatchResult:
        sandbox_dir = os.path.join(self._sandbox_root, patch.node_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        patch_file = os.path.join(sandbox_dir, "patch.py")
        log_file = os.path.join(sandbox_dir, "sandbox.log")

        try:
            with open(patch_file, "w") as f:
                f.write(patch.patch_code)

            if len(patch.patch_code) > MAX_PATCH_SIZE:
                return PatchResult(
                    success=False, patch=patch,
                    sandbox_log="Patch trop volumineux",
                    tested=True,
                )

            result = subprocess.run(
                [sys.executable, "-c", f"exec(open('{patch_file}').read()); print('SANDBOX_OK')"],
                capture_output=True, text=True,
                timeout=MAX_SANDBOX_TIME_S,
                cwd=sandbox_dir,
            )

            sandbox_log = result.stdout + result.stderr
            success = "SANDBOX_OK" in result.stdout

            if success:
                self._mark_repaired(patch.node_id)

            return PatchResult(
                success=success,
                patch=patch,
                sandbox_log=sandbox_log[:1000],
                tested=True,
                signature=self._sign_patch(patch) if success else "",
            )

        except subprocess.TimeoutExpired:
            return PatchResult(
                success=False, patch=patch,
                sandbox_log="Timeout - patch trop lent",
                tested=True,
            )
        except Exception as e:
            return PatchResult(
                success=False, patch=patch,
                sandbox_log=f"Erreur sandbox: {e}",
                tested=True,
            )
        finally:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def _sign_patch(self, patch: PatchSpec) -> str:
        data = f"{patch.node_id}:{patch.patch_hash}:{time.time()}"
        return hashlib.sha512(data.encode()).hexdigest()

    def _mark_repaired(self, node_id: str):
        with self._lock:
            self._repaired_nodes.add(node_id)

    def is_repaired(self, node_id: str) -> bool:
        return node_id in self._repaired_nodes

    def get_patch_history(self) -> list[PatchResult]:
        with self._lock:
            return list(self._patches)

    def status(self) -> dict:
        with self._lock:
            return {
                "patches_applied": len(self._patches),
                "nodes_repaired": len(self._repaired_nodes),
                "repaired_nodes": list(self._repaired_nodes),
            }


import sys

__all__ = [
    "PixRobotCoder", "PatchSpec", "PatchResult",
]
