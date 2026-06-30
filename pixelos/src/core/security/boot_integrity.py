#!/usr/bin/env python3
"""
BootIntegrity — Vérification cryptographique obligatoire au démarrage.

Séquence :
  1. Calcule SHA256 de tous les fichiers core/*.py
  2. Compare à la baseline signée stockée dans /var/db/pixelos/pixscudo/baseline.json
  3. Si mismatch → alerte critique sur IPC + refuse de démarrer les missions
  4. Si match → autorise le passage en mode MISSION_READY

Utilisation :
  from core.security.boot_integrity import check_boot_integrity
  result = check_boot_integrity()
  if not result["passed"]:
      sys.exit(1)  # ou mode dégradé
"""

import os
import sys
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CORE_DIRS = [
    "pixelos/src/core",
]

BASELINE_FILE = "/var/db/pixelos/pixscudo/baseline.json"
SIGNATURE_FILE = "/var/db/pixelos/pixscudo/baseline.sig"
INTEGRITY_LOG = "/var/log/pixelos/boot_integrity.log"
INTEGRITY_STATE = "/var/db/pixelos/pixscudo/integrity_state.json"

CRITICAL_MODULES = [
    "ipc.py", "config.py", "orchestrator.py", "pixstat.py",
    "pixscudo.py",
    "pixnet/pixmesh.py", "pixnet/pixdht.py",
    "pixhal/pixhal.py", "pixauto/pixauto.py",
    "pixkey/pixkey.py",
    "security/robot_firewall.py", "security/boot_integrity.py",
    "digital_twin/twin.py",
]


def log(msg: str):
    line = f"[{datetime.now().isoformat()}] {msg}"
    print(line, flush=True)
    try:
        Path(INTEGRITY_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(INTEGRITY_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def sha256_file(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def find_project_root() -> str:
    """Remonte jusqu'à trouver la racine du dépôt pixelos-agricol."""
    cwd = os.getcwd()
    for _ in range(5):
        if os.path.exists(os.path.join(cwd, "pixelos")) or \
           os.path.exists(os.path.join(cwd, "robots")):
            return cwd
        parent = os.path.dirname(cwd)
        if parent == cwd:
            break
        cwd = parent
    return os.getcwd()


def scan_core_files(root: str) -> dict:
    """Scanne tous les fichiers .py dans core/ et retourne {relpath: sha256}."""
    manifest = {}
    for core_dir in CORE_DIRS:
        full_path = os.path.join(root, core_dir)
        if not os.path.isdir(full_path):
            continue
        for dirpath, _, filenames in os.walk(full_path):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, fn)
                rel = os.path.relpath(fpath, root)
                digest = sha256_file(fpath)
                if digest:
                    manifest[rel] = digest
    return manifest


def create_baseline(root: str = "") -> dict:
    """Crée une baseline d'intégrité et la signe."""
    if not root:
        root = find_project_root()
    manifest = scan_core_files(root)
    baseline = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": root,
        "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
        "files": manifest,
        "total_files": len(manifest),
        "signature": "",
    }
    # Signature simple (à remplacer par GPG/clé matérielle)
    raw = json.dumps(manifest, sort_keys=True)
    baseline["signature"] = hashlib.sha256(raw.encode()).hexdigest()

    Path(BASELINE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)
    with open(SIGNATURE_FILE, "w") as f:
        f.write(baseline["signature"])

    log(f"Baseline créée: {len(manifest)} fichiers, signature={baseline['signature'][:16]}...")
    return baseline


def verify_baseline_signature(baseline: dict) -> bool:
    """Vérifie la signature de la baseline."""
    manifest = baseline.get("files", {})
    expected_sig = baseline.get("signature", "")
    if not expected_sig:
        return False
    raw = json.dumps(manifest, sort_keys=True)
    actual_sig = hashlib.sha256(raw.encode()).hexdigest()
    return actual_sig == expected_sig


def verify_integrity(baseline: dict, root: str = "") -> dict:
    """Compare les fichiers actuels à la baseline. Retourne les différences."""
    if not root:
        root = find_project_root()

    if not verify_baseline_signature(baseline):
        return {"passed": False, "error": "baseline signature invalid"}

    expected = baseline.get("files", {})
    current = scan_core_files(root)

    changes = []
    missing = []
    added = []

    all_paths = set(expected.keys()) | set(current.keys())

    for path in sorted(all_paths):
        if path not in expected:
            added.append(path)
            continue
        if path not in current:
            missing.append(path)
            continue
        if expected[path] != current[path]:
            changes.append({
                "file": path,
                "expected": expected[path][:16],
                "actual": current[path][:16],
            })

    return {
        "passed": len(changes) == 0 and len(missing) == 0,
        "total_expected": len(expected),
        "total_current": len(current),
        "files_changed": changes,
        "files_missing": missing,
        "files_added": added,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def load_baseline() -> Optional[dict]:
    try:
        with open(BASELINE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def save_integrity_state(result: dict):
    Path(INTEGRITY_STATE).parent.mkdir(parents=True, exist_ok=True)
    with open(INTEGRITY_STATE, "w") as f:
        json.dump(result, f, indent=2)


def check_boot_integrity(root: str = "") -> dict:
    """Point d'entrée principal : vérifie l'intégrité au démarrage.

    Retourne:
      {"passed": True, ...}  → tout est OK
      {"passed": False, ...} → alerte, ne pas démarrer les missions
    """
    log("=== Boot Integrity Check ===")

    if not root:
        root = find_project_root()
    log(f"Project root: {root}")

    baseline = load_baseline()
    if not baseline:
        log("WARNING: No baseline found. Creating baseline...")
        baseline = create_baseline(root)
        result = {
            "passed": True,
            "warning": "first_boot_baseline_created",
            "total_files": baseline["total_files"],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        save_integrity_state(result)
        log("Baseline created. Run again to verify.")
        return result

    result = verify_integrity(baseline, root)
    log(f"Integrity: {'PASS' if result['passed'] else 'FAIL'}")
    log(f"  Files expected: {result['total_expected']}")
    log(f"  Files current:  {result['total_current']}")
    if result.get("files_changed"):
        for c in result["files_changed"]:
            log(f"  CHANGED: {c['file']} (expected {c['expected']} != actual {c['actual']})")
    if result.get("files_missing"):
        for m in result["files_missing"]:
            log(f"  MISSING: {m}")
    if result.get("files_added"):
        for a in result["files_added"]:
            log(f"  ADDED: {a}")

    save_integrity_state(result)
    return result


def enforce_integrity_or_block(root: str = "") -> bool:
    """Vérifie l'intégrité et retourne False si blocage nécessaire.

    À appeler avant le démarrage des missions robot.
    """
    result = check_boot_integrity(root)
    if not result["passed"]:
        log("CRITICAL: Boot integrity check FAILED. Blocking mission start.")
        try:
            sys.path.insert(0, os.path.join(find_project_root(), "pixelos", "src"))
            from core.ipc import MessageBus, Message
            bus = MessageBus()
            bus.publish(Message("alert", "boot_integrity", "pixstat", {
                "type": "integrity_failure",
                "details": result,
            }))
        except Exception:
            pass
        return False
    return True


def main():
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "check"

    if action == "check":
        result = check_boot_integrity()
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    elif action == "create-baseline":
        baseline = create_baseline()
        print(json.dumps(baseline, indent=2))
        return 0
    elif action == "enforce":
        ok = enforce_integrity_or_block()
        print(json.dumps({"passed": ok}))
        return 0 if ok else 1
    else:
        print(f"Usage: {sys.argv[0]} [check|create-baseline|enforce]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
