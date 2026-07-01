"""
PixPowerManager — Gestion des cycles de charge/repos et budget énergétique.

Architecture:
  PowerBudget     → Budget disponible, alloué, marge
  ChargeSchedule  → Planification des cycles charge/repos
  SleepScheduler  → Mise en veille/réveil des robots inactifs
  BatteryHealth   → Suivi de santé des batteries (SOH, cycles)
  PixPowerManager → Orchestrateur power management robotique
"""

import time
import math
import threading
from dataclasses import dataclass, field
from typing import Optional
from enum import IntEnum


ROOT_DIR = __file__


class RobotPowerState(IntEnum):
    ACTIVE = 0
    IDLE = 1
    CHARGING = 2
    SLEEP = 3
    DOCKED = 4


POWER_STATE_NAMES = {
    RobotPowerState.ACTIVE: "active",
    RobotPowerState.IDLE: "idle",
    RobotPowerState.CHARGING: "charging",
    RobotPowerState.SLEEP: "sleep",
    RobotPowerState.DOCKED: "docked",
}


@dataclass
class PowerBudget:
    available_watts: float = 0.0
    allocated_watts: float = 0.0
    peak_demand_watts: float = 0.0
    headroom_watts: float = 0.0
    solar_input_watts: float = 0.0
    grid_input_watts: float = 0.0
    battery_output_watts: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "available_watts": round(self.available_watts, 1),
            "allocated_watts": round(self.allocated_watts, 1),
            "peak_demand_watts": round(self.peak_demand_watts, 1),
            "headroom_watts": round(self.headroom_watts, 1),
            "solar_input_watts": round(self.solar_input_watts, 1),
            "grid_input_watts": round(self.grid_input_watts, 1),
            "battery_output_watts": round(self.battery_output_watts, 1),
            "timestamp": self.timestamp,
        }


@dataclass
class RobotPowerEntry:
    robot_id: str
    nominal_watts: float = 100.0
    state: RobotPowerState = RobotPowerState.IDLE
    battery_soc_pct: float = 100.0
    battery_capacity_wh: float = 500.0
    cycle_count: int = 0
    sleep_until: float = 0.0
    charge_started_at: float = 0.0
    state_changed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "nominal_watts": self.nominal_watts,
            "state": POWER_STATE_NAMES.get(self.state, "unknown"),
            "battery_soc_pct": round(self.battery_soc_pct, 1),
            "battery_capacity_wh": round(self.battery_capacity_wh, 1),
            "cycle_count": self.cycle_count,
            "sleep_until": self.sleep_until,
            "state_changed_at": self.state_changed_at,
            "current_draw_watts": round(self._current_draw(), 1),
        }

    def _current_draw(self) -> float:
        if self.state == RobotPowerState.SLEEP:
            return self.nominal_watts * 0.02
        if self.state in (RobotPowerState.CHARGING, RobotPowerState.DOCKED):
            return -self.nominal_watts * 0.3
        if self.state == RobotPowerState.IDLE:
            return self.nominal_watts * 0.1
        return self.nominal_watts * 0.8


@dataclass
class ChargeSchedule:
    robot_id: str
    scheduled_at: float = 0.0
    duration_seconds: float = 1800.0
    reason: str = "scheduled"
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "scheduled_at": self.scheduled_at,
            "duration_seconds": self.duration_seconds,
            "reason": self.reason,
            "completed": self.completed,
        }


@dataclass
class BatteryHealthRecord:
    robot_id: str
    soh_pct: float = 100.0
    cycle_count: int = 0
    capacity_wh: float = 500.0
    internal_resistance_mohm: float = 50.0
    last_calibrated: float = 0.0

    def to_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "soh_pct": round(self.soh_pct, 1),
            "cycle_count": self.cycle_count,
            "capacity_wh": round(self.capacity_wh, 1),
            "internal_resistance_mohm": round(self.internal_resistance_mohm, 2),
            "last_calibrated": self.last_calibrated,
        }


CHARGING_STATES = {RobotPowerState.CHARGING, RobotPowerState.DOCKED}
AWAKE_STATES = {RobotPowerState.ACTIVE, RobotPowerState.IDLE, RobotPowerState.CHARGING}


class PixPowerManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._robots: dict[str, RobotPowerEntry] = {}
        self._budget = PowerBudget(timestamp=time.time())
        self._charge_queue: list[ChargeSchedule] = []
        self._health_records: dict[str, BatteryHealthRecord] = {}
        self._history: list[dict] = []
        self._max_history = 1000
        self._solar_input_watts = 0.0
        self._grid_input_watts = 0.0
        self._battery_storage_wh = 5000.0
        self._battery_soc_pct = 80.0
        self._running = False
        self._tick_interval = 10.0
        self._thread: Optional[threading.Thread] = None

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def register_robot(self, robot_id: str, nominal_watts: float = 100.0,
                       battery_capacity_wh: float = 500.0) -> RobotPowerEntry:
        with self._lock:
            entry = RobotPowerEntry(
                robot_id=robot_id,
                nominal_watts=nominal_watts,
                battery_capacity_wh=battery_capacity_wh,
            )
            self._robots[robot_id] = entry
            if robot_id not in self._health_records:
                self._health_records[robot_id] = BatteryHealthRecord(
                    robot_id=robot_id,
                    capacity_wh=battery_capacity_wh,
                )
            return entry

    def unregister_robot(self, robot_id: str) -> bool:
        with self._lock:
            if robot_id in self._robots:
                del self._robots[robot_id]
                return True
            return False

    def set_state(self, robot_id: str, state: RobotPowerState) -> bool:
        with self._lock:
            entry = self._robots.get(robot_id)
            if not entry:
                return False
            entry.state = state
            entry.state_changed_at = time.time()
            if state == RobotPowerState.CHARGING:
                entry.charge_started_at = time.time()
            return True

    def set_soc(self, robot_id: str, soc_pct: float) -> bool:
        with self._lock:
            entry = self._robots.get(robot_id)
            if not entry:
                return False
            entry.battery_soc_pct = max(0.0, min(100.0, soc_pct))
            return True

    def set_power_inputs(self, solar_watts: float = 0.0,
                         grid_watts: float = 0.0,
                         battery_soc_pct: float = 80.0,
                         battery_storage_wh: float = 5000.0):
        with self._lock:
            self._solar_input_watts = solar_watts
            self._grid_input_watts = grid_watts
            self._battery_soc_pct = battery_soc_pct
            self._battery_storage_wh = battery_storage_wh

    def schedule_charge(self, robot_id: str, delay_seconds: float = 0.0,
                        duration_seconds: float = 1800.0,
                        reason: str = "scheduled") -> ChargeSchedule:
        sched = ChargeSchedule(
            robot_id=robot_id,
            scheduled_at=time.time() + delay_seconds,
            duration_seconds=duration_seconds,
            reason=reason,
        )
        with self._lock:
            self._charge_queue.append(sched)
        return sched

    def get_budget(self) -> PowerBudget:
        with self._lock:
            return PowerBudget(
                available_watts=self._budget.available_watts,
                allocated_watts=self._budget.allocated_watts,
                peak_demand_watts=self._budget.peak_demand_watts,
                headroom_watts=self._budget.headroom_watts,
                solar_input_watts=self._budget.solar_input_watts,
                grid_input_watts=self._budget.grid_input_watts,
                battery_output_watts=self._budget.battery_output_watts,
                timestamp=self._budget.timestamp,
            )

    def get_robot(self, robot_id: str) -> Optional[RobotPowerEntry]:
        with self._lock:
            entry = self._robots.get(robot_id)
            return entry

    def list_robots(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._robots.values()]

    def list_charge_schedule(self) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self._charge_queue]

    def get_health(self, robot_id: str) -> Optional[BatteryHealthRecord]:
        with self._lock:
            rec = self._health_records.get(robot_id)
            return rec

    def list_health(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._health_records.values()]

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(reversed(self._history))[:limit]

    def summary(self) -> dict:
        with self._lock:
            total = len(self._robots)
            active = sum(1 for r in self._robots.values() if r.state == RobotPowerState.ACTIVE)
            charging = sum(1 for r in self._robots.values() if r.state in CHARGING_STATES)
            idle = sum(1 for r in self._robots.values() if r.state == RobotPowerState.IDLE)
            sleeping = sum(1 for r in self._robots.values() if r.state == RobotPowerState.SLEEP)
            low_battery = sum(1 for r in self._robots.values() if r.battery_soc_pct < 20.0)
            total_draw = sum(r._current_draw() for r in self._robots.values())
            return {
                "total_robots": total,
                "active": active,
                "charging": charging,
                "idle": idle,
                "sleeping": sleeping,
                "low_battery": low_battery,
                "total_draw_watts": round(total_draw, 1),
                "budget": self._budget.to_dict(),
                "charge_queue_length": len(self._charge_queue),
                "battery_storage_wh": self._battery_storage_wh,
                "battery_soc_pct": round(self._battery_soc_pct, 1),
            }

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def tick(self):
        now = time.time()
        with self._lock:
            self._compute_budget(now)
            self._process_charge_schedule(now)
            self._auto_sleep_wake(now)
            self._age_batteries(now)

    def _compute_budget(self, now: float):
        total_draw = sum(r._current_draw() for r in self._robots.values())
        charging_draw = sum(
            r.nominal_watts * 0.3 for r in self._robots.values()
            if r.state in CHARGING_STATES
        )
        total_allocated = abs(total_draw) + charging_draw
        peak_demand = sum(r.nominal_watts for r in self._robots.values())
        total_input = self._solar_input_watts + self._grid_input_watts

        battery_available = 0.0
        if self._battery_soc_pct > 20.0:
            battery_available = self._battery_storage_wh * (self._battery_soc_pct / 100.0) * 0.1

        available = total_input + battery_available
        self._budget = PowerBudget(
            available_watts=available,
            allocated_watts=total_allocated,
            peak_demand_watts=peak_demand,
            headroom_watts=max(0.0, available - total_allocated),
            solar_input_watts=self._solar_input_watts,
            grid_input_watts=self._grid_input_watts,
            battery_output_watts=battery_available,
            timestamp=now,
        )

        self._history.append(self._budget.to_dict())
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def _process_charge_schedule(self, now: float):
        remaining = []
        for sched in self._charge_queue:
            if sched.completed:
                continue
            if now >= sched.scheduled_at:
                entry = self._robots.get(sched.robot_id)
                if entry and entry.battery_soc_pct < 95.0:
                    entry.state = RobotPowerState.CHARGING
                    entry.charge_started_at = now
                    entry.state_changed_at = now
                sched.completed = True
            else:
                remaining.append(sched)

        for entry in self._robots.values():
            if entry.state == RobotPowerState.CHARGING:
                elapsed = now - entry.charge_started_at
                charge_gain = (elapsed / 3600.0) * 0.3 * 100.0
                entry.battery_soc_pct = min(100.0, entry.battery_soc_pct + charge_gain)
                if entry.battery_soc_pct >= 95.0:
                    entry.state = RobotPowerState.DOCKED
                    entry.state_changed_at = now
                    health = self._health_records.get(entry.robot_id)
                    if health:
                        health.cycle_count += 1
        self._charge_queue = remaining

    def _auto_sleep_wake(self, now: float):
        for entry in self._robots.values():
            if entry.state == RobotPowerState.SLEEP and now >= entry.sleep_until:
                entry.state = RobotPowerState.IDLE
                entry.state_changed_at = now
            elif entry.state == RobotPowerState.IDLE:
                idle_time = now - entry.state_changed_at
                if idle_time > 600.0 and entry.battery_soc_pct < 30.0:
                    entry.state = RobotPowerState.SLEEP
                    entry.sleep_until = now + 3600.0
                    entry.state_changed_at = now

    def _age_batteries(self, now: float):
        for robot_id, entry in self._robots.items():
            health = self._health_records.get(robot_id)
            if not health:
                continue
            cycles = health.cycle_count
            health.soh_pct = max(60.0, 100.0 - cycles * 0.02)
            health.capacity_wh = entry.battery_capacity_wh * (health.soh_pct / 100.0)
            health.internal_resistance_mohm = 50.0 + cycles * 0.5
            health.last_calibrated = now

    def _run(self):
        while self._running:
            self.tick()
            time.sleep(self._tick_interval)
