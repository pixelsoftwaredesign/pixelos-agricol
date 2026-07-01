"""
PixMode — Mode Manager pour Pixel OS.

Gère la bascule sécurisée entre modes de contrôle :
  - AUTO : pilotage par l'essaim (PixSwarm)
  - MANUAL : contrôle direct par un technicien humain
  - IDLE : veille active / jeu (PixBalloon)
  - EMERGENCY : arrêt d'urgence (contourne tout)
  - MAINTENANCE : extraction de logs, mise à jour

Architecture de sécurité hiérarchique :
  1. Hardware E-Stop (coupe puissance)
  2. PixModeManager (software mode switch)
  3. SafetyFilter (empêche commandes dangereuses)
  4. DeadmanSwitch (arrêt si perte signal opérateur)
"""

import time
import threading
import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Enums ──────────────────────────────────────────────────

class RobotMode(enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"
    IDLE = "idle"
    EMERGENCY = "emergency"
    MAINTENANCE = "maintenance"


class ModeTransition(enum.Enum):
    """Transitions autorisées entre modes."""
    AUTO_TO_MANUAL = ("auto", "manual")
    AUTO_TO_IDLE = ("auto", "idle")
    AUTO_TO_EMERGENCY = ("auto", "emergency")
    MANUAL_TO_AUTO = ("manual", "auto")
    MANUAL_TO_IDLE = ("manual", "idle")
    MANUAL_TO_EMERGENCY = ("manual", "emergency")
    IDLE_TO_AUTO = ("idle", "auto")
    IDLE_TO_MANUAL = ("idle", "manual")
    IDLE_TO_EMERGENCY = ("idle", "emergency")
    EMERGENCY_TO_AUTO = ("emergency", "auto")
    EMERGENCY_TO_MANUAL = ("emergency", "manual")
    EMERGENCY_TO_MAINTENANCE = ("emergency", "maintenance")
    MAINTENANCE_TO_IDLE = ("maintenance", "idle")

    @classmethod
    def is_allowed(cls, frm: str, to: str) -> bool:
        return (frm, to) in {(t.value[0], t.value[1]) for t in cls}


# ── Dataclasses ────────────────────────────────────────────

@dataclass
class OperatorAuth:
    """Authentification d'un opérateur humain."""
    operator_id: str
    role: str  # "technician", "supervisor", "admin"
    token: str
    authenticated_at: float = 0.0
    expires_at: float = 0.0

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


@dataclass
class ManualCommand:
    """Commande manuelle envoyée par l'opérateur."""
    linear_vel: float = 0.0   # m/s
    angular_vel: float = 0.0  # rad/s
    timestamp: float = 0.0
    sequence: int = 0

    def to_dict(self) -> dict:
        return {
            "linear_vel": self.linear_vel,
            "angular_vel": self.angular_vel,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


@dataclass
class SafetyStatus:
    """État de sécurité courant du robot."""
    obstacle_ahead: bool = False
    obstacle_distance: float = 999.0
    human_detected: bool = False
    battery_critical: bool = False
    tilt_angle: float = 0.0
    all_clear: bool = True


# ── SafetyFilter ──────────────────────────────────────────

class SafetyFilter:
    """Filtre de sécurité pour les commandes manuelles.

    Empêche l'opérateur de diriger le robot vers un obstacle.
    En mode MANUAL, la commande humaine passe par ce filtre avant
    d'être exécutée.
    """

    def __init__(self):
        # Distances de sécurité par type d'obstacle
        self._safety_distances = {
            "humain": 2.0,
            "animal": 1.5,
            "mur": 0.5,
            "arbre": 0.8,
            "obstacle_inconnu": 1.0,
        }
        self._last_status = SafetyStatus()

    def update_sensors(self, status: SafetyStatus):
        self._last_status = status

    def filter_command(self, cmd: ManualCommand) -> tuple[bool, ManualCommand, str]:
        """Filtrer une commande manuelle.

        Retourne (acceptée, commande filtrée, raison).
        """
        status = self._last_status

        # Priorité 1 : Humain détecté → STOP
        if status.human_detected:
            return (False, ManualCommand(), "HUMAIN détecté - arrêt imposé")

        # Priorité 2 : Obstacle trop proche dans la direction
        if status.obstacle_ahead and cmd.linear_vel > 0:
            dist = status.obstacle_distance
            threshold = self._safety_distances.get("obstacle_inconnu", 1.0)
            if dist < threshold * 2.0:
                # Ralentissement progressif
                ratio = max(0.0, (dist - 0.3) / (threshold * 2.0 - 0.3))
                filtered = ManualCommand(
                    linear_vel=cmd.linear_vel * ratio,
                    angular_vel=cmd.angular_vel,
                    timestamp=cmd.timestamp,
                    sequence=cmd.sequence,
                )
                if ratio < 0.1:
                    return (False, ManualCommand(), f"Obstacle à {dist:.1f}m - arrêt")
                return (True, filtered, f"Freinage ({ratio:.0%})")

        # Priorité 3 : Batterie critique → ralentissement
        if status.battery_critical and abs(cmd.linear_vel) > 0.3:
            filtered = ManualCommand(
                linear_vel=0.3 * (1 if cmd.linear_vel > 0 else -1),
                angular_vel=cmd.angular_vel,
                timestamp=cmd.timestamp,
                sequence=cmd.sequence,
            )
            return (True, filtered, "Batterie faible - vitesse limitée")

        return (True, cmd, "ok")


# ── DeadmanSwitch ──────────────────────────────────────────

class DeadmanSwitch:
    """Surveille la présence de l'opérateur.

    Si aucun signal (heartbeat) n'est reçu pendant `timeout` secondes,
    déclenche un EMERGENCY STOP.
    """

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
        self._last_signal = time.monotonic()
        self._armed = False
        self._on_timeout: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def set_on_timeout(self, callback: Callable):
        self._on_timeout = callback

    def arm(self):
        self._armed = True
        self._last_signal = time.monotonic()
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._monitor, daemon=True)
            self._thread.start()

    def disarm(self):
        self._armed = False
        self._running = False

    def kick(self):
        """L'opérateur envoie un signal 'je suis là'."""
        self._last_signal = time.monotonic()

    def _monitor(self):
        while self._running and self._armed:
            elapsed = time.monotonic() - self._last_signal
            if elapsed > self.timeout:
                if self._on_timeout:
                    self._on_timeout()
                self._armed = False
                break
            time.sleep(0.1)

    @property
    def time_since_last_signal(self) -> float:
        return time.monotonic() - self._last_signal

    @property
    def is_healthy(self) -> bool:
        return not self._armed or self.time_since_last_signal < self.timeout


# ── PixModeManager ─────────────────────────────────────────

class PixModeManager:
    """Gestionnaire central des modes de contrôle.

    Usage:
        mm = PixModeManager()
        mm.on_mode_change = lambda mode: print(f"Nouveau mode: {mode}")

        # Passage en MANUAL avec authentification
        auth = OperatorAuth(operator_id="tech_01", role="technician",
                            token="abc123", expires_at=time.monotonic() + 3600)
        ok, reason = mm.request_mode("manual", auth=auth)

        # En MANUAL, l'opérateur envoie des commandes
        ok, cmd, reason = mm.send_manual_command(ManualCommand(linear_vel=0.5))

        # Deadman switch : heartbeat opérateur
        mm.deadman_kick()

        # Retour en AUTO
        ok, reason = mm.request_mode("auto")
    """

    # Transitions qui nécessitent authentification
    AUTH_REQUIRED = {
        RobotMode.MANUAL,
        RobotMode.MAINTENANCE,
    }

    # Modes où le DeadmanSwitch est actif
    DEADMAN_MODES = {RobotMode.MANUAL}

    # Modes où le SafetyFilter est actif
    FILTER_MODES = {RobotMode.MANUAL}

    def __init__(self, deadman_timeout: float = 2.0):
        self._mode = RobotMode.AUTO
        self._previous_mode = RobotMode.AUTO
        self._lock = threading.Lock()
        self._auth: Optional[OperatorAuth] = None

        # Sous-systèmes
        self.safety = SafetyFilter()
        self.deadman = DeadmanSwitch(timeout=deadman_timeout)
        self.deadman.set_on_timeout(self._on_deadman_timeout)

        # État
        self._manual_command_count = 0
        self._mode_changes = 0
        self._history: list[dict] = []
        self._suspended_processes: list[str] = []

        # Callbacks
        self.on_mode_change: Optional[Callable] = None
        self.on_emergency: Optional[Callable] = None
        self.on_command_filtered: Optional[Callable] = None

    # ── Propriétés ─────────────────────────────────────────

    @property
    def mode(self) -> RobotMode:
        return self._mode

    @property
    def mode_name(self) -> str:
        return self._mode.value

    @property
    def is_auto(self) -> bool:
        return self._mode == RobotMode.AUTO

    @property
    def is_manual(self) -> bool:
        return self._mode == RobotMode.MANUAL

    @property
    def is_emergency(self) -> bool:
        return self._mode == RobotMode.EMERGENCY

    # ── Changement de mode ─────────────────────────────────

    def request_mode(self, target: str, auth: OperatorAuth = None,
                     reason: str = "") -> tuple[bool, str]:
        """Demander un changement de mode.

        Retourne (succès, message).
        """
        try:
            target_mode = RobotMode(target)
        except ValueError:
            return (False, f"Mode inconnu: {target}")

        with self._lock:
            current = self._mode

            # Vérifier que la transition est autorisée
            if not ModeTransition.is_allowed(current.value, target_mode.value):
                return (False,
                        f"Transition {current.value} → {target_mode.value} interdite")

            # Vérifier l'authentification si nécessaire
            if target_mode in self.AUTH_REQUIRED:
                if not auth or not auth.is_valid():
                    return (False, "Authentification requise")
                self._auth = auth

            # Exécuter la transition
            self._previous_mode = current
            self._mode = target_mode
            self._mode_changes += 1

            # Actions spécifiques au mode
            self._on_mode_enter(target_mode)

            # Journalisation
            entry = {
                "from": current.value,
                "to": target_mode.value,
                "auth": auth.operator_id if auth else None,
                "reason": reason,
                "timestamp": time.monotonic(),
            }
            self._history.append(entry)

        if self.on_mode_change:
            self.on_mode_change(target_mode)

        return (True, f"Mode {target_mode.value} activé")

    def _on_mode_enter(self, mode: RobotMode):
        """Actions déclenchées à l'entrée d'un mode."""
        if mode == RobotMode.EMERGENCY:
            self.deadman.disarm()
            if self.on_emergency:
                self.on_emergency()
        elif mode in self.DEADMAN_MODES:
            self.deadman.arm()
        elif mode == RobotMode.AUTO:
            self.deadman.disarm()
            self._resume_processes()
        elif mode == RobotMode.MANUAL:
            self._suspend_auto_processes()
        elif mode == RobotMode.MAINTENANCE:
            self.deadman.disarm()
            self._suspend_auto_processes()

    # ── Commandes manuelles ────────────────────────────────

    def send_manual_command(self, cmd: ManualCommand) -> tuple[bool, ManualCommand, str]:
        """Envoyer une commande manuelle (passe par le SafetyFilter).

        Retourne (acceptée, commande filtrée, message).
        """
        if self._mode != RobotMode.MANUAL:
            return (False, ManualCommand(), "Pas en mode MANUAL")

        # Mettre à jour le DeadmanSwitch
        self.deadman.kick()
        cmd.sequence = self._manual_command_count
        cmd.timestamp = time.monotonic()
        self._manual_command_count += 1

        # Filtrer
        if self._mode in self.FILTER_MODES:
            accepted, filtered, msg = self.safety.filter_command(cmd)
            if not accepted:
                if self.on_command_filtered:
                    self.on_command_filtered(cmd, msg)
                return (False, filtered, msg)
            if filtered != cmd:
                if self.on_command_filtered:
                    self.on_command_filtered(cmd, msg)
            cmd = filtered

        return (True, cmd, "ok")

    # ── Deadman Switch ─────────────────────────────────────

    def deadman_kick(self):
        """L'opérateur confirme sa présence."""
        self.deadman.kick()

    def _on_deadman_timeout(self):
        """Le DeadmanSwitch a expiré → EMERGENCY."""
        with self._lock:
            self._previous_mode = self._mode
            self._mode = RobotMode.EMERGENCY
            self._mode_changes += 1
            self._history.append({
                "from": self._previous_mode.value,
                "to": "emergency",
                "auth": None,
                "reason": "DeadmanSwitch timeout - perte signal opérateur",
                "timestamp": time.monotonic(),
            })
        print("[PixMode] DEADMAN_TIMEOUT → EMERGENCY")
        if self.on_mode_change:
            self.on_mode_change(RobotMode.EMERGENCY)
        if self.on_emergency:
            self.on_emergency()

    # ── Suspension de processus ────────────────────────────

    def _suspend_auto_processes(self):
        """Simule la suspension des processus autonomes.

        En conditions réelles, enverrait SIGSTOP aux processus
        de navigation et de mission.
        """
        self._suspended_processes = [
            "pixswarm_heartbeat",
            "pixvision_detector",
            "pixnav_planner",
        ]

    def _resume_processes(self):
        self._suspended_processes = []

    # ── Sélecteur physique (simulé) ────────────────────────

    def physical_selector(self, position: str) -> tuple[bool, str]:
        """Simule le commutateur physique à clé.

        Positions : "AUTO", "MANUAL", "OFF"
        """
        pos = position.upper()
        if pos == "AUTO":
            return self.request_mode("auto", reason="Sélecteur physique")
        elif pos == "MANUAL":
            return self.request_mode("manual", reason="Sélecteur physique")
        elif pos == "OFF":
            return self.request_mode("emergency", reason="Sélecteur physique OFF")
        return (False, f"Position inconnue: {position}")

    # ── Statut ─────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "mode": self._mode.value,
            "previous_mode": self._previous_mode.value,
            "is_auto": self.is_auto,
            "is_manual": self.is_manual,
            "is_emergency": self.is_emergency,
            "operator": self._auth.operator_id if self._auth else None,
            "deadman_armed": self.deadman._armed,
            "deadman_time_since_signal": round(self.deadman.time_since_last_signal, 2),
            "deadman_healthy": self.deadman.is_healthy,
            "safety": {
                "obstacle_ahead": self.safety._last_status.obstacle_ahead,
                "obstacle_distance": self.safety._last_status.obstacle_distance,
                "human_detected": self.safety._last_status.human_detected,
                "all_clear": self.safety._last_status.all_clear,
            },
            "suspended_processes": self._suspended_processes,
            "mode_changes": self._mode_changes,
            "manual_commands": self._manual_command_count,
        }

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    # ── Cleanup ────────────────────────────────────────────

    def close(self):
        self.deadman.disarm()


__all__ = [
    "PixModeManager",
    "RobotMode", "ModeTransition",
    "OperatorAuth", "ManualCommand", "SafetyStatus",
    "SafetyFilter", "DeadmanSwitch",
]
