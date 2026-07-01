"""
Tests pour PixPowerManager — Gestion des cycles de charge/repos.
"""

import time
import pytest
from src.core.pixpowermanager import (
    PixPowerManager,
    RobotPowerState,
    POWER_STATE_NAMES,
)


class TestPowerStates:
    def test_state_enum_values(self):
        assert RobotPowerState.ACTIVE == 0
        assert RobotPowerState.IDLE == 1
        assert RobotPowerState.CHARGING == 2
        assert RobotPowerState.SLEEP == 3
        assert RobotPowerState.DOCKED == 4

    def test_state_names(self):
        assert POWER_STATE_NAMES[RobotPowerState.ACTIVE] == "active"
        assert POWER_STATE_NAMES[RobotPowerState.IDLE] == "idle"
        assert POWER_STATE_NAMES[RobotPowerState.CHARGING] == "charging"
        assert POWER_STATE_NAMES[RobotPowerState.SLEEP] == "sleep"
        assert POWER_STATE_NAMES[RobotPowerState.DOCKED] == "docked"


class TestPowerManagerCreate:
    def test_create(self):
        pm = PixPowerManager()
        assert pm is not None
        assert pm.summary()["total_robots"] == 0
        pm.stop()

    def test_summary_structure(self):
        pm = PixPowerManager()
        s = pm.summary()
        assert "total_robots" in s
        assert "active" in s
        assert "charging" in s
        assert "idle" in s
        assert "sleeping" in s
        assert "low_battery" in s
        assert "total_draw_watts" in s
        assert "budget" in s
        assert "charge_queue_length" in s
        assert "battery_soc_pct" in s
        pm.stop()


class TestRobotRegistration:
    def test_register_robot(self):
        pm = PixPowerManager()
        entry = pm.register_robot("RBT_01")
        assert entry.robot_id == "RBT_01"
        assert entry.nominal_watts == 100.0
        assert entry.battery_capacity_wh == 500.0
        assert entry.state == RobotPowerState.IDLE
        assert entry.battery_soc_pct == 100.0
        pm.stop()

    def test_register_multiple(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=200.0)
        pm.register_robot("RBT_02", nominal_watts=50.0, battery_capacity_wh=300.0)
        robots = pm.list_robots()
        assert len(robots) == 2
        ids = {r["robot_id"] for r in robots}
        assert ids == {"RBT_01", "RBT_02"}
        pm.stop()

    def test_unregister(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        assert pm.unregister_robot("RBT_01") is True
        assert pm.unregister_robot("NONEXIST") is False
        assert len(pm.list_robots()) == 0
        pm.stop()

    def test_register_creates_health_record(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", battery_capacity_wh=750.0)
        health = pm.get_health("RBT_01")
        assert health is not None
        assert health.robot_id == "RBT_01"
        assert health.capacity_wh == 750.0
        assert health.soh_pct == 100.0
        pm.stop()

    def test_register_does_not_duplicate_health(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        h1 = pm.get_health("RBT_01")
        pm.register_robot("RBT_01")
        h2 = pm.get_health("RBT_01")
        assert h1 is h2
        pm.stop()


class TestRobotState:
    def test_set_state(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        assert pm.set_state("RBT_01", RobotPowerState.ACTIVE) is True
        entry = pm.get_robot("RBT_01")
        assert entry.state == RobotPowerState.ACTIVE
        pm.stop()

    def test_set_state_unknown_robot(self):
        pm = PixPowerManager()
        assert pm.set_state("NONEXIST", RobotPowerState.ACTIVE) is False
        pm.stop()

    def test_set_soc(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        assert pm.set_soc("RBT_01", 45.0) is True
        entry = pm.get_robot("RBT_01")
        assert entry.battery_soc_pct == 45.0
        pm.stop()

    def test_set_soc_unknown(self):
        pm = PixPowerManager()
        assert pm.set_soc("NONEXIST", 50.0) is False
        pm.stop()

    def test_set_soc_clamps(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", -10.0)
        assert pm.get_robot("RBT_01").battery_soc_pct == 0.0
        pm.set_soc("RBT_01", 150.0)
        assert pm.get_robot("RBT_01").battery_soc_pct == 100.0
        pm.stop()


class TestPowerBudget:
    def test_initial_budget(self):
        pm = PixPowerManager()
        b = pm.get_budget()
        assert b.available_watts == 0.0
        assert b.allocated_watts == 0.0
        assert b.headroom_watts >= 0.0
        pm.stop()

    def test_budget_with_solar_input(self):
        pm = PixPowerManager()
        pm.set_power_inputs(solar_watts=2000.0, grid_watts=500.0)
        pm.tick()
        b = pm.get_budget()
        assert b.solar_input_watts == 2000.0
        assert b.grid_input_watts == 500.0
        assert b.available_watts > 0.0
        pm.stop()

    def test_budget_with_robots(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=100.0)
        pm.register_robot("RBT_02", nominal_watts=200.0)
        pm.set_state("RBT_01", RobotPowerState.ACTIVE)
        pm.set_state("RBT_02", RobotPowerState.ACTIVE)
        pm.set_power_inputs(solar_watts=1000.0)
        pm.tick()
        b = pm.get_budget()
        assert b.peak_demand_watts == 300.0
        assert b.allocated_watts > 0.0
        pm.stop()

    def test_budget_unknown(self):
        pm = PixPowerManager()
        b = pm.get_budget()
        assert b.timestamp > 0
        pm.stop()


class TestChargeScheduling:
    def test_schedule_charge(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", battery_capacity_wh=500.0)
        pm.set_soc("RBT_01", 15.0)
        sched = pm.schedule_charge("RBT_01", delay_seconds=0.0,
                                   duration_seconds=1800.0, reason="low_battery")
        assert sched.robot_id == "RBT_01"
        assert sched.duration_seconds == 1800.0
        assert sched.reason == "low_battery"
        assert sched.completed is False
        pm.stop()

    def test_schedule_charge_processes(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 10.0)
        pm.schedule_charge("RBT_01", delay_seconds=0.0)
        pm.tick()
        entry = pm.get_robot("RBT_01")
        assert entry.state == RobotPowerState.CHARGING
        pm.stop()

    def test_charge_increases_soc(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 10.0)
        pm.set_state("RBT_01", RobotPowerState.CHARGING)
        pm.get_robot("RBT_01").charge_started_at = time.time() - 3600
        pm.tick()
        entry = pm.get_robot("RBT_01")
        assert entry.battery_soc_pct > 10.0
        pm.stop()

    def test_charge_completes_at_95(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 94.0)
        pm.set_state("RBT_01", RobotPowerState.CHARGING)
        pm.get_robot("RBT_01").charge_started_at = time.time() - 3600
        pm.tick()
        entry = pm.get_robot("RBT_01")
        assert entry.state == RobotPowerState.DOCKED
        pm.stop()

    def test_list_charge_schedule(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.schedule_charge("RBT_01", delay_seconds=300.0, reason="test")
        schedules = pm.list_charge_schedule()
        assert len(schedules) == 1
        assert schedules[0]["reason"] == "test"
        assert schedules[0]["completed"] is False
        pm.stop()


class TestSleepWake:
    def test_idle_robot_sleeps_when_low_battery(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 20.0)
        pm.set_state("RBT_01", RobotPowerState.IDLE)
        entry = pm.get_robot("RBT_01")
        entry.state_changed_at = time.time() - 700
        pm.tick()
        assert entry.state == RobotPowerState.SLEEP
        pm.stop()

    def test_sleep_robot_wakes_after_time(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_state("RBT_01", RobotPowerState.SLEEP)
        entry = pm.get_robot("RBT_01")
        entry.sleep_until = time.time() - 10
        pm.tick()
        assert entry.state == RobotPowerState.IDLE
        pm.stop()

    def test_high_battery_idle_does_not_sleep(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 80.0)
        pm.set_state("RBT_01", RobotPowerState.IDLE)
        entry = pm.get_robot("RBT_01")
        entry.state_changed_at = time.time() - 700
        pm.tick()
        assert entry.state == RobotPowerState.IDLE
        pm.stop()

    def test_active_robot_does_not_sleep(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 10.0)
        pm.set_state("RBT_01", RobotPowerState.ACTIVE)
        pm.tick()
        assert pm.get_robot("RBT_01").state == RobotPowerState.ACTIVE
        pm.stop()


class TestBatteryHealth:
    def test_initial_health(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        health = pm.get_health("RBT_01")
        assert health.soh_pct == 100.0
        assert health.cycle_count == 0
        assert health.internal_resistance_mohm == 50.0
        pm.stop()

    def test_aging_reduces_soh(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", battery_capacity_wh=500.0)
        pm.set_state("RBT_01", RobotPowerState.CHARGING)
        entry = pm.get_robot("RBT_01")
        entry.battery_soc_pct = 100.0
        entry.charge_started_at = time.time() - 7200
        for _ in range(5):
            pm.tick()
        health = pm.get_health("RBT_01")
        assert health.cycle_count >= 1
        assert health.soh_pct < 100.0
        pm.stop()

    def test_health_record_update(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", battery_capacity_wh=1000.0)
        health = pm.get_health("RBT_01")
        assert health.capacity_wh == 1000.0
        pm.stop()

    def test_list_health(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.register_robot("RBT_02")
        records = pm.list_health()
        assert len(records) == 2
        pm.stop()


class TestPowerManagerHistory:
    def test_history_records_budget(self):
        pm = PixPowerManager()
        pm.set_power_inputs(solar_watts=1500.0)
        pm.tick()
        history = pm.get_history(limit=5)
        assert len(history) >= 1
        assert "solar_input_watts" in history[0]
        pm.stop()

    def test_history_limit(self):
        pm = PixPowerManager()
        for _ in range(20):
            pm.tick()
        assert len(pm.get_history(limit=5)) <= 5
        pm.stop()


class TestCurrentDraw:
    def test_active_draw(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=100.0)
        pm.set_state("RBT_01", RobotPowerState.ACTIVE)
        d = pm.get_robot("RBT_01").to_dict()
        assert d["current_draw_watts"] == 80.0

    def test_idle_draw(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=100.0)
        pm.set_state("RBT_01", RobotPowerState.IDLE)
        d = pm.get_robot("RBT_01").to_dict()
        assert d["current_draw_watts"] == 10.0

    def test_sleep_draw(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=100.0)
        pm.set_state("RBT_01", RobotPowerState.SLEEP)
        d = pm.get_robot("RBT_01").to_dict()
        assert d["current_draw_watts"] == 2.0

    def test_charging_draw_negative(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", nominal_watts=100.0)
        pm.set_state("RBT_01", RobotPowerState.CHARGING)
        d = pm.get_robot("RBT_01").to_dict()
        assert d["current_draw_watts"] == -30.0


class TestIntegration:
    def test_full_cycle(self):
        pm = PixPowerManager()
        pm.set_power_inputs(solar_watts=3000.0, grid_watts=500.0)
        pm.register_robot("RBT_01", nominal_watts=150.0, battery_capacity_wh=600.0)
        pm.register_robot("RBT_02", nominal_watts=200.0, battery_capacity_wh=800.0)
        pm.set_state("RBT_01", RobotPowerState.ACTIVE)
        pm.set_state("RBT_02", RobotPowerState.ACTIVE)
        pm.tick()
        s = pm.summary()
        assert s["total_robots"] == 2
        assert s["active"] == 2
        assert s["total_draw_watts"] == 280.0
        pm.stop()

    def test_low_battery_detection(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.register_robot("RBT_02")
        pm.set_soc("RBT_01", 15.0)
        pm.set_soc("RBT_02", 80.0)
        s = pm.summary()
        assert s["low_battery"] == 1

    def test_charge_schedule_and_process(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01")
        pm.set_soc("RBT_01", 10.0)
        pm.schedule_charge("RBT_01", delay_seconds=0.0, duration_seconds=3600.0)
        pm.tick()
        schedules = pm.list_charge_schedule()
        assert len(schedules) == 0 or schedules[0]["completed"]
        entry = pm.get_robot("RBT_01")
        assert entry.state == RobotPowerState.CHARGING

    def test_set_power_inputs(self):
        pm = PixPowerManager()
        pm.set_power_inputs(solar_watts=2500.0, grid_watts=1000.0,
                            battery_soc_pct=60.0, battery_storage_wh=10000.0)
        pm.tick()
        b = pm.get_budget()
        assert b.solar_input_watts == 2500.0
        assert b.grid_input_watts == 1000.0

    def test_health_degrades_with_cycles(self):
        pm = PixPowerManager()
        pm.register_robot("RBT_01", battery_capacity_wh=500.0)
        health = pm.get_health("RBT_01")
        initial_soh = health.soh_pct
        pm.set_state("RBT_01", RobotPowerState.CHARGING)
        entry = pm.get_robot("RBT_01")
        entry.battery_soc_pct = 100.0
        entry.charge_started_at = time.time() - 7200
        for _ in range(50):
            pm.tick()
        assert health.cycle_count > 0
        assert health.soh_pct < initial_soh
        assert health.internal_resistance_mohm > 50.0
