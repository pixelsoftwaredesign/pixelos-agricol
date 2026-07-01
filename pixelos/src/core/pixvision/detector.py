"""
PixVision — Détection d'objets non connectés (Vision IA).

Pipeline:
  Frame caméra → PixDetector.infer() → DetectionResult
  → SafetyReactor.on_detection() → PixIPC / PixHAL / EnvironmentMap

Fallback simulation intégrée pour développement sans GPU.
"""

import json
import math
import random
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pixvision"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MAP_FILE = DATA_DIR / "environment_map.json"
LOG_FILE = DATA_DIR / "detection_log.jsonl"


# ── Modèles de données ──────────────────────────────────────

@dataclass
class DetectionResult:
    """Résultat unique de détection d'objet."""
    class_name: str          # "HUMAIN", "ANIMAL", "ARBRE", "OBSTACLE_INCONNU"
    confidence: float        # 0..1
    x: float                 # position X relative écran (0..1)
    y: float                 # position Y relative écran (0..1)
    width: float             # largeur relative boîte (0..1)
    height: float            # hauteur relative boîte (0..1)
    distance: float = 0.0    # distance estimée en mètres
    depth: float = 0.0       # profondeur (si stéréo/LiDAR)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return asdict(self)

    @property
    def is_living(self) -> bool:
        return self.class_name in ("HUMAIN", "ANIMAL")

    @property
    def is_static(self) -> bool:
        return self.class_name in ("ARBRE", "ROCHER", "BATIMENT", "CLOTURE")

    @property
    def is_unknown(self) -> bool:
        return self.class_name == "OBSTACLE_INCONNU"

    @property
    def priority(self) -> int:
        """Priorité de réaction : 0=faible, 1=moyenne, 2=critique."""
        if self.class_name == "HUMAIN":
            return 2
        if self.class_name == "ANIMAL":
            return 1
        if self.is_unknown:
            return 1
        return 0


@dataclass
class ObstableCarte:
    """Obstacle enregistré dans l'EnvironmentMap."""
    class_name: str
    x: float
    y: float
    radius: float          # zone de sécurité en mètres
    confidence: float
    first_seen: str
    last_seen: str
    hit_count: int = 1

    def to_dict(self):
        return asdict(self)


# ── Simulateur d'inférence (fallback dev) ───────────────────

class SimulatedInference:
    """Simule YOLO ONNX avec des détections cycliques pour le développement."""

    CLASSES = ["HUMAIN", "ANIMAL", "ARBRE", "ROCHER",
               "BATIMENT", "CLOTURE", "OBSTACLE_INCONNU"]
    CYCLE = ["HUMAIN", "ANIMAL", "ARBRE", "OBSTACLE_INCONNU",
             "ROCHER", "ARBRE", "ARBRE", "ANIMAL", "CLOTURE", "BATIMENT"]

    def __init__(self):
        self._index = 0

    def infer(self, frame=None) -> list[DetectionResult]:
        """Retourne 2-5 détections simulées."""
        now = datetime.now(timezone.utc).isoformat()
        results = []
        count = random.randint(2, 5)
        for _ in range(count):
            cls = random.choice(self.CLASSES)
            # Bias toward current cycle
            if random.random() < 0.4:
                cls = self.CYCLE[self._index % len(self.CYCLE)]
                self._index += 1
            results.append(DetectionResult(
                class_name=cls,
                confidence=random.uniform(0.65, 0.98),
                x=random.uniform(0.1, 0.9),
                y=random.uniform(0.1, 0.9),
                width=random.uniform(0.05, 0.3),
                height=random.uniform(0.05, 0.4),
                distance=random.uniform(1.0, 25.0),
                timestamp=now,
            ))
        return results


# ── Filtre de Kalman 2D ─────────────────────────────────────

class KalmanFilter2D:
    """Filtre de Kalman simple pour suivi de trajectoire."""

    def __init__(self, dt: float = 0.1):
        self.dt = dt
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.P = [[1, 0, 0, 0],
                  [0, 1, 0, 0],
                  [0, 0, 10, 0],
                  [0, 0, 0, 10]]
        self.Q = [[0.1, 0, 0, 0],
                  [0, 0.1, 0, 0],
                  [0, 0, 0.1, 0],
                  [0, 0, 0, 0.1]]
        self.R = 0.5
        self.initialized = False

    def predict(self) -> tuple[float, float]:
        dt = self.dt
        F = [[1, 0, dt, 0],
             [0, 1, 0, dt],
             [0, 0, 1, 0],
             [0, 0, 0, 1]]
        # Prédiction naïve des prochaines coordonnées
        px = self.x + self.vx * dt
        py = self.y + self.vy * dt
        return px, py

    def update(self, zx: float, zy: float):
        if not self.initialized:
            self.x, self.y = zx, zy
            self.initialized = True
            return
        # Prédiction
        px, py = self.predict()
        # Correction simple (moving average pondéré)
        alpha = 0.7
        self.x = alpha * px + (1 - alpha) * zx
        self.y = alpha * py + (1 - alpha) * zy
        self.vx = (self.x - px) / self.dt
        self.vy = (self.y - py) / self.dt

    def predicted_position(self, steps: int = 5) -> tuple[float, float]:
        px = self.x + self.vx * self.dt * steps
        py = self.y + self.vy * self.dt * steps
        return px, py


# ── Moteur de réaction sécurisée ─────────────────────────────

class SafetyReactor:
    """Logique de réaction aux détections.

    Comportement par type :
      HUMAIN    → STOP_IMMEDIAT + alarme sonore + arrêt moteur
      ANIMAL    → RALENTIR + distance sécurité augmentée
      ARBRE     → Mise à jour carte statique
      INCONNU   → Contournement large + marquage carte
    """

    def __init__(self, on_emergency: Callable = None,
                 on_alarm: Callable = None,
                 on_slow: Callable = None):
        self._emergency_cb = on_emergency
        self._alarm_cb = on_alarm
        self._slow_cb = on_slow
        self._last_reaction_time = 0.0
        self._cooldown = 1.0  # secondes entre réactions identiques
        self._log: list[dict] = []

    def on_detection(self, result: DetectionResult) -> dict:
        """Réagir à une détection. Retourne l'action prise."""
        now = time.monotonic()
        action = {
            "action": "RIEN",
            "class": result.class_name,
            "confidence": result.confidence,
            "distance": result.distance,
            "timestamp": result.timestamp,
        }

        if result.priority == 2 and result.class_name == "HUMAIN":
            action["action"] = "STOP_IMMEDIAT"
            action["reason"] = "Humain détecté"
            self._emergency_brake(result)
            self._sound_alarm(result)
            # Log
            self._log_event("EMERGENCY_STOP", result)
            return action

        if result.priority == 1 and result.class_name == "ANIMAL":
            action["action"] = "RALENTIR"
            action["reason"] = f"Animal détecté à {result.distance:.1f}m"
            self._slow_down(result)
            self._log_event("SLOW_DOWN", result)
            return action

        if result.is_unknown:
            action["action"] = "CONTOURNER"
            action["reason"] = "Obstacle non classifié – contournement large"
            self._log_event("BYPASS", result)
            return action

        if result.is_static:
            action["action"] = "MAJ_CARTE"
            action["reason"] = f"{result.class_name} – mise à jour carte statique"
            self._log_event("MAP_UPDATE", result)
            return action

        return action

    def _emergency_brake(self, result: DetectionResult):
        if self._emergency_cb:
            self._emergency_cb(result)
            return
        # Simulation : log
        msg = (
            f"[EMERGENCY] STOP_IMMEDIAT: {result.class_name} "
            f"à {result.distance:.1f}m (conf={result.confidence:.0%})"
        )
        print(msg)

    def _sound_alarm(self, result: DetectionResult):
        if self._alarm_cb:
            self._alarm_cb(result)
            return
        print(f"[ALARME] Activation sonore: présence {result.class_name}")

    def _slow_down(self, result: DetectionResult):
        if self._slow_cb:
            self._slow_cb(result)
            return
        print(f"[RALENTIR] Vitesse réduite: {result.class_name} à {result.distance:.1f}m")

    def _log_event(self, event_type: str, result: DetectionResult):
        entry = {
            "event": event_type,
            "class": result.class_name,
            "confidence": result.confidence,
            "distance": result.distance,
            "timestamp": result.timestamp,
        }
        self._log.append(entry)

        # Append to JSONL log
        try:
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def get_log(self, limit: int = 50) -> list[dict]:
        return self._log[-limit:]

    def clear_log(self):
        self._log.clear()


# ── Carte d'environnement ────────────────────────────────────

class EnvironmentMap:
    """Carte statique des obstacles connus.

    Stockée dans data/pixvision/environment_map.json.
    Permet au robot de savoir où sont les obstacles avant de naviguer.
    """

    def __init__(self):
        self._obstacles: dict[str, ObstableCarte] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if MAP_FILE.exists():
            try:
                data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
                for entry in data:
                    obs = ObstableCarte(**entry)
                    key = f"{obs.class_name}_{obs.x:.2f}_{obs.y:.2f}"
                    self._obstacles[key] = obs
            except Exception:
                pass

    def _save(self):
        with self._lock:
            data = [asdict(o) for o in self._obstacles.values()]
            MAP_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def update(self, class_name: str, x: float, y: float,
               confidence: float, radius: float = None) -> ObstableCarte:
        """Ajouter ou mettre à jour un obstacle sur la carte."""
        if radius is None:
            radius = self._default_radius(class_name)

        now = datetime.now(timezone.utc).isoformat()
        key = f"{class_name}_{x:.2f}_{y:.2f}"

        with self._lock:
            if key in self._obstacles:
                obs = self._obstacles[key]
                obs.last_seen = now
                obs.hit_count += 1
                obs.confidence = max(obs.confidence, confidence)
                obs.radius = max(obs.radius, radius)
            else:
                obs = ObstableCarte(
                    class_name=class_name, x=x, y=y,
                    radius=radius, confidence=confidence,
                    first_seen=now, last_seen=now,
                )
                self._obstacles[key] = obs

        self._save()
        return obs

    def _default_radius(self, class_name: str) -> float:
        """Rayon de sécurité par type d'obstacle (mètres)."""
        radii = {
            "HUMAIN": 3.0,
            "ANIMAL": 5.0,
            "ARBRE": 2.0,
            "ROCHER": 1.5,
            "BATIMENT": 1.0,
            "CLOTURE": 1.0,
            "OBSTACLE_INCONNU": 4.0,
        }
        return radii.get(class_name, 2.0)

    def check_collision(self, x: float, y: float,
                        robot_radius: float = 0.5) -> Optional[ObstableCarte]:
        """Vérifie si une position (x,y) entre en collision avec un obstacle connu."""
        with self._lock:
            for obs in self._obstacles.values():
                dist = math.sqrt((obs.x - x)**2 + (obs.y - y)**2)
                if dist < (obs.radius + robot_radius):
                    return obs
        return None

    def get_obstacles(self, class_name: str = None) -> list[dict]:
        with self._lock:
            obs_list = list(self._obstacles.values())
        if class_name:
            obs_list = [o for o in obs_list if o.class_name == class_name]
        return [asdict(o) for o in sorted(
            obs_list, key=lambda x: x.last_seen, reverse=True
        )]

    def clear(self):
        with self._lock:
            self._obstacles.clear()
        self._save()

    def stats(self) -> dict:
        with self._lock:
            by_type = {}
            for o in self._obstacles.values():
                by_type[o.class_name] = by_type.get(o.class_name, 0) + 1
            return {
                "total": len(self._obstacles),
                "by_type": by_type,
            }


# ── Détecteur principal ─────────────────────────────────────

class PixDetector:
    """Pipeline complet de détection → réaction → carte.

    Boucle principale :
      1. Capturer frame (callback ou simulée)
      2. Inférence YOLO (ou simulation)
      3. SafetyReactor.on_detection() pour chaque résultat
      4. EnvironmentMap.update() pour obstacles statiques
      5. Boucle à ~10 FPS
    """

    def __init__(self, on_emergency: Callable = None,
                 on_alarm: Callable = None,
                 on_slow: Callable = None):
        self.inference = SimulatedInference()
        self.reactor = SafetyReactor(
            on_emergency=on_emergency,
            on_alarm=on_alarm,
            on_slow=on_slow,
        )
        self.map = EnvironmentMap()
        self.kalman = KalmanFilter2D(dt=0.1)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_callback: Optional[Callable] = None
        self._fps = 10.0
        self._frame_count = 0
        self._last_actions: list[dict] = []

    def set_frame_source(self, callback: Callable):
        """Callback(frame) → retourne une frame pour inférence."""
        self._frame_callback = callback

    def process_frame(self, frame=None) -> list[dict]:
        """Traiter une frame unique : inférence → réaction → carte.

        Retourne les actions prises pour chaque détection.
        """
        results = self.inference.infer(frame)
        actions = []

        for det in results:
            # Filtrer les confiances trop basses
            if det.confidence < 0.4:
                continue

            # Suivi Kalman pour objets vivants
            if det.is_living:
                self.kalman.update(det.x, det.y)
                pred = self.kalman.predicted_position(5)
                det.x = pred[0]
                det.y = pred[1]

            # Réaction
            action = self.reactor.on_detection(det)
            actions.append(action)

            # Mise à jour carte pour obstacles statiques/inconnus
            if det.is_static or det.is_unknown:
                self.map.update(
                    class_name=det.class_name,
                    x=det.x, y=det.y,
                    confidence=det.confidence,
                )

        self._frame_count += 1
        self._last_actions = actions
        return actions

    def _loop(self):
        """Boucle d'inférence en continu."""
        while self._running:
            frame = None
            if self._frame_callback:
                frame = self._frame_callback()
            self.process_frame(frame)
            time.sleep(1.0 / self._fps)

    def start(self):
        """Démarrer la boucle de détection dans un thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrêter la boucle de détection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def status(self) -> dict:
        return {
            "running": self._running,
            "fps": self._fps,
            "frames_processed": self._frame_count,
            "detection_count": len(self.reactor.get_log()),
            "recent_actions": self._last_actions[-5:] if self._last_actions else [],
        }

    def emergency_stop(self, reason: str = "manual"):
        """Arrêt d'urgence manuel."""
        self.reactor._log_event("EMERGENCY_STOP_MANUAL",
                                DetectionResult(class_name=reason, confidence=1.0, x=0, y=0, width=0, height=0))
        print(f"[EMERGENCY] Arrêt manuel: {reason}")


# ── Singleton ───────────────────────────────────────────────

detector = PixDetector()
env_map = detector.map

__all__ = [
    "DetectionResult", "ObstableCarte", "SimulatedInference",
    "KalmanFilter2D", "SafetyReactor", "EnvironmentMap",
    "PixDetector", "detector", "env_map",
]
