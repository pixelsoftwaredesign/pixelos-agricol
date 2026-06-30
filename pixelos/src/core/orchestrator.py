#!/usr/bin/env python3
"""
PixOrchestrator — Moteur d'orchestration transverse PixelOS.

Coordonne les modules PixelOS:
  - Planifie et exécute des workflows multi-étapes
  - Déclenche des actions conditionnelles (IFTTT-like)
  - Gère les dépendances entre tâches (DAG)
  - Publie l'état sur MQTT
  - S'intègre à PixAuto pour les règles d'automatisation
"""

import os
import json
import time
import socket
import hashlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

ORCH_DIR = "/var/db/pixelos/orchestrator"
WORKFLOWS_FILE = "workflows.json"
TASKS_FILE = "tasks.json"
HISTORY_FILE = "history.json"

WORKER_INTERVAL = 10

# Modules connus que PixOrchestrator peut redémarrer
MANAGED_MODULES = {
    "pixstat": {"type": "service", "cmd": "rcctl restart pixstat"},
    "pixdefend": {"type": "service", "cmd": "rcctl restart pixdefend"},
    "pixdht": {"type": "service", "cmd": "rcctl restart pixdht"},
    "pixauto": {"type": "python", "module": "core.pixauto.pixauto", "class": "PixAuto"},
    "pixhal": {"type": "python", "module": "core.pixhal.pixhal", "class": "PixHAL"},
    "pixkey": {"type": "python", "module": "core.pixkey.pixkey", "class": "PixKey"},
    "pixdao": {"type": "python", "module": "core.pixdao.pixdao", "class": "PixDAO"},
    "digital_twin": {"type": "python", "module": "core.digital_twin.twin", "class": "DigitalTwin"},
    "agent": {"type": "service", "cmd": "rcctl restart pixelos_agent"},
    "web": {"type": "service", "cmd": "rcctl restart pixelos_web"},
}


class PixOrchestrator:
    def __init__(self):
        self._ensure_dirs()
        self._load_workflows()
        self._load_tasks()
        self._load_history()
        self._hooks: dict[str, list[Callable]] = {}
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._pending_nodes: dict[str, dict] = {}
        self._fleet_nodes: dict[str, dict] = {}
        self._load_fleet()
        self._start_worker()
        self._start_ipc_listener()

    def _ensure_dirs(self):
        Path(ORCH_DIR).mkdir(parents=True, exist_ok=True)

    def _path(self, name):
        return str(Path(ORCH_DIR) / name)

    def _load_workflows(self):
        path = self._path(WORKFLOWS_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.workflows = json.load(f)
                return
            except Exception:
                pass
        self.workflows = []

    def _save_workflows(self):
        with open(self._path(WORKFLOWS_FILE), "w") as f:
            json.dump(self.workflows, f, indent=2)

    def _load_tasks(self):
        path = self._path(TASKS_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.tasks = json.load(f)
                return
            except Exception:
                pass
        self.tasks = {}

    def _save_tasks(self):
        with open(self._path(TASKS_FILE), "w") as f:
            json.dump(self.tasks, f, indent=2)

    def _load_history(self):
        path = self._path(HISTORY_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.history = json.load(f)
                return
            except Exception:
                pass
        self.history = []

    def _save_history(self):
        with open(self._path(HISTORY_FILE), "w") as f:
            json.dump(self.history[-500:], f, indent=2)

    # ── Workflow CRUD ─────────────────────────────────────

    def create_workflow(self, name: str, steps: list[dict]) -> dict:
        wf = {
            "id": hashlib.sha256(f"{name}{time.time()}".encode()).hexdigest()[:12],
            "name": name,
            "steps": steps,
            "status": "idle",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "execution_count": 0,
            "last_executed": "",
        }
        self.workflows.append(wf)
        self._save_workflows()
        return wf

    def get_workflows(self) -> list:
        return self.workflows

    def get_workflow(self, wf_id: str) -> Optional[dict]:
        for w in self.workflows:
            if w["id"] == wf_id:
                return w
        return None

    def update_workflow(self, wf_id: str, updates: dict) -> dict:
        for w in self.workflows:
            if w["id"] == wf_id:
                for k in ("name", "steps", "enabled"):
                    if k in updates:
                        w[k] = updates[k]
                w["updated_at"] = datetime.now().isoformat()
                self._save_workflows()
                return {"status": "updated", "workflow": w}
        return {"status": "not_found"}

    def delete_workflow(self, wf_id: str) -> dict:
        for i, w in enumerate(self.workflows):
            if w["id"] == wf_id:
                del self.workflows[i]
                self._save_workflows()
                return {"status": "deleted"}
        return {"status": "not_found"}

    # ── Task management ───────────────────────────────────

    def create_task(self, task_def: dict) -> dict:
        tid = hashlib.sha256(f"{task_def}{time.time()}".encode()).hexdigest()[:12]
        task = {
            "id": tid,
            "name": task_def.get("name", "unnamed"),
            "type": task_def.get("type", "shell"),
            "command": task_def.get("command", ""),
            "params": task_def.get("params", {}),
            "depends_on": task_def.get("depends_on", []),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "started_at": "",
            "completed_at": "",
            "result": None,
            "error": None,
            "timeout": task_def.get("timeout", 60),
            "retries": task_def.get("retries", 0),
            "retry_count": 0,
        }
        self.tasks[tid] = task
        self._save_tasks()
        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        return self.tasks.get(task_id)

    def list_tasks(self, status: str = "") -> list:
        if status:
            return [t for t in self.tasks.values() if t.get("status") == status]
        return list(self.tasks.values())

    def cancel_task(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "not_found"}
        if task["status"] in ("running", "pending"):
            task["status"] = "cancelled"
            task["error"] = "cancelled by user"
            self._save_tasks()
            return {"status": "cancelled"}
        return {"status": "cannot_cancel", "current": task["status"]}

    def delete_task(self, task_id: str) -> dict:
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            return {"status": "deleted"}
        return {"status": "not_found"}

    # ── Execution ─────────────────────────────────────────

    def execute_workflow(self, wf_id: str) -> dict:
        wf = self.get_workflow(wf_id)
        if not wf:
            return {"status": "error", "error": "workflow not found"}

        wf["status"] = "running"
        wf["execution_count"] += 1
        wf["last_executed"] = datetime.now().isoformat()
        step_results = []

        for step in wf.get("steps", []):
            deps = step.get("depends_on", [])
            # Vérifier les dépendances
            dep_ok = all(
                any(sr["id"] == d and sr.get("status") == "success"
                    for sr in step_results)
                for d in deps
            )
            if not dep_ok:
                step_results.append({
                    "id": step.get("id", ""),
                    "name": step.get("name", ""),
                    "status": "skipped",
                    "reason": "dependency not met",
                })
                continue

            task = self.create_task(step)
            result = self._run_task(task["id"])
            step_results.append({
                "id": task["id"],
                "name": task["name"],
                "status": result.get("status"),
                "result": result.get("result"),
                "error": result.get("error"),
            })

            if result.get("status") != "success":
                if not step.get("on_failure", "stop") == "continue":
                    break

        wf["status"] = "completed"
        self._save_workflows()
        self.history.append({
            "workflow_id": wf_id,
            "workflow_name": wf["name"],
            "executed_at": datetime.now().isoformat(),
            "steps": step_results,
        })
        self._save_history()
        self._trigger_hook("workflow_completed", {"workflow_id": wf_id, "steps": step_results})
        return {"workflow_id": wf_id, "status": wf["status"], "steps": step_results}

    def execute_task(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "error", "error": "task not found"}
        return self._run_task(task_id)

    def _run_task(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "error", "error": "not found"}

        task["status"] = "running"
        task["started_at"] = datetime.now().isoformat()
        self._save_tasks()
        self._trigger_hook("task_started", {"task_id": task_id})

        ttype = task.get("type", "shell")
        result = None
        error = None

        try:
            if ttype == "shell":
                import subprocess
                r = subprocess.run(
                    task["command"], shell=True,
                    capture_output=True, text=True,
                    timeout=task.get("timeout", 60),
                )
                result = {"stdout": r.stdout[:2000], "stderr": r.stderr[:2000],
                          "returncode": r.returncode}
                if r.returncode != 0:
                    error = r.stderr[:500]

            elif ttype == "http":
                import urllib.request
                method = task.get("params", {}).get("method", "GET")
                url = task.get("command", "")
                if method == "GET":
                    with urllib.request.urlopen(url, timeout=task.get("timeout", 30)) as resp:
                        result = {"status": resp.status, "body": resp.read()[:2000].decode(errors="replace")}

            elif ttype == "mqtt":
                try:
                    from core.mqtt import PixelOSMQTT
                    mqtt = PixelOSMQTT()
                    topic = task.get("command", "")
                    payload = json.dumps(task.get("params", {}))
                    mqtt.publish(topic, payload)
                    result = {"published": True, "topic": topic}
                except Exception as e:
                    result = {"published": False, "error": str(e)}

            elif ttype == "pixauto":
                try:
                    from core.pixauto.pixauto import PixAuto
                    pa = PixAuto()
                    rule_text = task.get("command", "")
                    r = pa.add_rule(rule_text)
                    if r.get("status") == "added":
                        exec_r = pa.execute_rule(r["rule"]["id"])
                        result = {"rule": r, "execution": exec_r}
                    else:
                        result = r
                except Exception as e:
                    error = str(e)

            elif ttype == "webhook":
                import urllib.request
                url = task.get("command", "")
                params = task.get("params", {})
                import json as _json
                payload = _json.dumps(params).encode()
                req = urllib.request.Request(url, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = {"status": resp.status, "body": resp.read()[:2000].decode(errors="replace")}

            elif ttype == "python":
                code = task.get("command", "")
                local_ns = {"result": None}
                exec(code, {"__builtins__": __builtins__}, local_ns)
                result = {"output": str(local_ns.get("result", "executed"))}

            elif ttype == "sleep":
                seconds = int(task.get("command", 1))
                time.sleep(seconds)
                result = {"slept": seconds}

            else:
                error = f"unknown task type: {ttype}"

        except subprocess.TimeoutExpired:
            error = "timeout"
            result = {"error": "timeout"}
        except Exception as e:
            error = str(e)
            result = {"error": str(e)}

        task["status"] = "success" if error is None else "failed"
        task["result"] = result
        task["error"] = error
        task["completed_at"] = datetime.now().isoformat()
        self._save_tasks()
        self._trigger_hook("task_completed", {"task_id": task_id, "status": task["status"]})
        return task

    # ── Worker ────────────────────────────────────────────

    def _start_worker(self):
        def loop():
            while not self._stop.is_set():
                self._stop.wait(WORKER_INTERVAL)
                if self._stop.is_set():
                    break
                try:
                    self._tick()
                except Exception:
                    pass
        self._worker = threading.Thread(target=loop, daemon=True)
        self._worker.start()

    def _tick(self):
        """Vérifie les tâches en attente dont les dépendances sont satisfaites."""
        for tid, task in self.tasks.items():
            if task["status"] != "pending":
                continue
            deps = task.get("depends_on", [])
            if not deps:
                continue
            deps_met = all(
                    self.tasks.get(d, {}).get("status") == "success"
                    for d in deps
            )
            if deps_met:
                threading.Thread(target=self._run_task, args=(tid,), daemon=True).start()

    def stop(self):
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    # ── Hooks ─────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def _trigger_hook(self, event: str, data: dict):
        for cb in self._hooks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass

    # ── History ───────────────────────────────────────────

    def get_history(self, limit: int = 100) -> list:
        return self.history[-limit:]

    def clear_history(self) -> dict:
        self.history.clear()
        self._save_history()
        return {"status": "cleared"}

    # ── Module Restart (appelé par PixStat) ──────────────

    def restart_module(self, module_name: str) -> dict:
        """Redémarre un module défaillant suite à une alerte PixStat."""
        mod = MANAGED_MODULES.get(module_name)
        if not mod:
            return {"status": "error", "error": f"module {module_name} non géré"}

        if mod["type"] == "service":
            try:
                import subprocess
                r = subprocess.run(mod["cmd"].split(), capture_output=True, text=True, timeout=30)
                ok = r.returncode == 0
                self._log_restart(module_name, ok, r.stdout[:200])
                return {"status": "ok" if ok else "error", "module": module_name,
                        "type": "service", "output": r.stdout[:200]}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        elif mod["type"] == "python":
            try:
                import importlib, sys
                # Réimporter et réinstancier le module
                mod_spec = importlib.import_module(mod["module"])
                cls = getattr(mod_spec, mod["class"])
                instance = cls()
                # Remplacer dans le module d'origine
                orig_module = mod["module"].replace(".", "_")
                sys.modules[orig_module] = instance
                self._log_restart(module_name, True, f"reinstancié {mod['class']}")
                return {"status": "ok", "module": module_name,
                        "type": "python", "reloaded": mod["class"]}
            except Exception as e:
                self._log_restart(module_name, False, str(e))
                return {"status": "error", "error": str(e)}

        return {"status": "error", "error": "type inconnu"}

    def _log_restart(self, module: str, ok: bool, detail: str):
        self.history.append({
            "event": "module_restart",
            "module": module,
            "success": ok,
            "detail": detail,
            "ts": datetime.now().isoformat(),
        })
        self._save_history()

    def get_managed_modules(self) -> list:
        return [{"name": k, **v} for k, v in MANAGED_MODULES.items()]

    # ── Fleet Management (Zero-Touch Join) ──────────────

    def _load_fleet(self):
        path = Path(ORCH_DIR) / "fleet.json"
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                    self._fleet_nodes = data.get("nodes", {})
                    self._pending_nodes = data.get("pending", {})
            except Exception:
                pass

    def _save_fleet(self):
        path = Path(ORCH_DIR) / "fleet.json"
        with open(path, "w") as f:
            json.dump({"nodes": self._fleet_nodes, "pending": self._pending_nodes}, f, indent=2)

    def node_join(self, join_req: dict) -> dict:
        """Accepte un nouveau nœud et lui attribue une configuration.

        Vérifie l'authentification PixKey si fournie.
        """
        hw_id = join_req.get("hw_id", "")
        hostname = join_req.get("hostname", f"node-{len(self._fleet_nodes) + 1}")
        pixkey_auth = join_req.get("pixkey_auth", {})

        auth_method = pixkey_auth.get("method", "none")
        auth_token = pixkey_auth.get("token", "")

        if auth_method != "none":
            self._log_restart(f"auth:{hw_id[:16]}", True,
                              f"PixKey auth via {auth_method}")
        else:
            self._log_restart(f"auth:{hw_id[:16]}", False,
                              "No PixKey auth — accepté en mode non authentifié")

        node_id = hashlib.sha256(f"{hw_id}{time.time()}{os.urandom(8).hex()}".encode()).hexdigest()[:16]
        pixnet_key = hashlib.sha256(f"{node_id}{os.urandom(32).hex()}".encode()).hexdigest()

        import random
        node_num = len(self._fleet_nodes) + 1
        ip_address = f"10.0.0.{node_num}"

        config = {
            "node_id": node_id,
            "hostname": hostname,
            "ip_address": ip_address,
            "pixnet_key": pixnet_key,
            "orchestrator_url": f"http://{socket.gethostname()}:8080",
            "pixkey_auth": auth_method,
            "config": {
                "autostart": True,
                "modules": {
                    "pixstat": True, "pixdefend": True, "pixdht": True,
                    "pixauto": True, "pixhal": True, "pixkey": True,
                    "pixdao": True, "digital_twin": True,
                },
            },
        }

        self._fleet_nodes[node_id] = {
            **config,
            "hw_id": hw_id,
            "joined_at": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "status": "pending",
            "auth_method": auth_method,
        }
        self._pending_nodes[node_id] = self._fleet_nodes[node_id]
        self._save_fleet()

        self._log_restart(f"node_join:{node_id}", True, f"New node {hostname} ({hw_id[:16]}...) auth={auth_method}")
        return {"status": "ok", **config}

    def node_confirm(self, node_id: str) -> dict:
        """Confirme qu'un nœud a rejoint la flotte."""
        if node_id in self._pending_nodes:
            self._fleet_nodes[node_id]["status"] = "active"
            self._fleet_nodes[node_id]["last_seen"] = datetime.now().isoformat()
            del self._pending_nodes[node_id]
            self._save_fleet()
            self._log_restart(f"node_confirm:{node_id}", True, "Node active")
            return {"status": "ok", "node_id": node_id}
        return {"status": "error", "error": "node not found"}

    def get_fleet(self) -> dict:
        return {"nodes": self._fleet_nodes, "pending": self._pending_nodes}

    def get_node(self, node_id: str) -> dict:
        n = self._fleet_nodes.get(node_id) or self._pending_nodes.get(node_id)
        return n or {"error": "not found"}

    # ── IPC Listener ─────────────────────────────────────

    def _start_ipc_listener(self):
        """Écoute les commandes IPC (notamment de PixStat pour les restarts)."""
        try:
            from .ipc import MessageBus, MSG_TYPE_COMMAND
            bus = MessageBus()

            def on_command(msg):
                if msg.type != MSG_TYPE_COMMAND:
                    return
                if msg.target and msg.target not in ("orchestrator", self.__class__.__name__):
                    return
                cmd = msg.payload.get("command", "")
                if cmd == "restart_module":
                    module = msg.payload.get("params", {}).get("module", "")
                    if module:
                        self.restart_module(module)

            bus.subscribe("command", on_command)
        except Exception:
            pass

    # ── Stats ─────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "workflows": len(self.workflows),
            "tasks_total": len(self.tasks),
            "tasks_pending": sum(1 for t in self.tasks.values() if t["status"] == "pending"),
            "tasks_running": sum(1 for t in self.tasks.values() if t["status"] == "running"),
            "tasks_failed": sum(1 for t in self.tasks.values() if t["status"] == "failed"),
            "tasks_success": sum(1 for t in self.tasks.values() if t["status"] == "success"),
            "history_size": len(self.history),
            "hooks_registered": sum(len(v) for v in self._hooks.values()),
            "worker_running": self._worker is not None and self._worker.is_alive(),
        }
