"""
Tests unitaires pour PixModeManager.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.pixmode import (
    PixModeManager, RobotMode, ModeTransition,
    OperatorAuth, ManualCommand, SafetyStatus,
    SafetyFilter, DeadmanSwitch,
)


def test_default_mode():
    mm = PixModeManager()
    assert mm.mode == RobotMode.AUTO
    assert mm.is_auto
    assert not mm.is_manual
    assert not mm.is_emergency


def test_request_mode_auto_to_manual():
    mm = PixModeManager()
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    ok, msg = mm.request_mode("manual", auth=auth)
    assert ok
    assert mm.is_manual


def test_request_mode_auto_to_manual_no_auth():
    mm = PixModeManager()
    ok, msg = mm.request_mode("manual")
    assert not ok
    assert "Authentification" in msg
    assert mm.is_auto


def test_request_mode_invalid_transition():
    mm = PixModeManager()
    ok, msg = mm.request_mode("maintenance")
    assert not ok
    assert "interdite" in msg


def test_request_mode_unknown():
    mm = PixModeManager()
    ok, msg = mm.request_mode("hyperdrive")
    assert not ok
    assert "inconnu" in msg


def test_mode_transition_allowed():
    assert ModeTransition.is_allowed("auto", "manual")
    assert ModeTransition.is_allowed("auto", "idle")
    assert ModeTransition.is_allowed("manual", "auto")
    assert ModeTransition.is_allowed("emergency", "auto")
    assert not ModeTransition.is_allowed("idle", "maintenance")
    assert not ModeTransition.is_allowed("auto", "maintenance")


def test_manual_command_in_auto():
    mm = PixModeManager()
    cmd = ManualCommand(linear_vel=0.5)
    accepted, filtered, msg = mm.send_manual_command(cmd)
    assert not accepted
    assert "Pas en mode MANUAL" in msg


def test_manual_command_in_manual():
    mm = PixModeManager()
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    mm.request_mode("manual", auth=auth)
    cmd = ManualCommand(linear_vel=0.5)
    accepted, filtered, msg = mm.send_manual_command(cmd)
    assert accepted
    assert filtered.linear_vel == 0.5


def test_safety_filter_human_stop():
    sf = SafetyFilter()
    sf.update_sensors(SafetyStatus(human_detected=True))
    cmd = ManualCommand(linear_vel=0.5)
    accepted, filtered, msg = sf.filter_command(cmd)
    assert not accepted
    assert "HUMAIN" in msg


def test_safety_filter_obstacle_brake():
    sf = SafetyFilter()
    sf.update_sensors(SafetyStatus(obstacle_ahead=True, obstacle_distance=0.6))
    cmd = ManualCommand(linear_vel=0.5)
    accepted, filtered, msg = sf.filter_command(cmd)
    assert accepted or not accepted
    if accepted:
        assert filtered.linear_vel < 0.5


def test_safety_filter_obstacle_stop():
    sf = SafetyFilter()
    sf.update_sensors(SafetyStatus(obstacle_ahead=True, obstacle_distance=0.2))
    cmd = ManualCommand(linear_vel=0.5)
    accepted, filtered, msg = sf.filter_command(cmd)
    assert not accepted
    assert "arrêt" in msg


def test_safety_filter_low_battery():
    sf = SafetyFilter()
    sf.update_sensors(SafetyStatus(battery_critical=True))
    cmd = ManualCommand(linear_vel=1.0)
    accepted, filtered, msg = sf.filter_command(cmd)
    assert accepted
    assert filtered.linear_vel == 0.3


def test_deadman_switch_arm():
    ds = DeadmanSwitch(timeout=0.3)
    ds.arm()
    assert ds._armed
    assert ds.is_healthy


def test_deadman_switch_kick():
    ds = DeadmanSwitch(timeout=1.0)
    ds.arm()
    ds.kick()
    t0 = ds._last_signal
    time.sleep(0.05)
    ds.kick()
    assert ds._last_signal > t0


def test_deadman_switch_timeout():
    triggered = []
    def on_timeout():
        triggered.append(True)
    ds = DeadmanSwitch(timeout=0.2)
    ds.set_on_timeout(on_timeout)
    ds.arm()
    time.sleep(0.3)
    assert len(triggered) > 0
    assert not ds._armed


def test_physical_selector():
    mm = PixModeManager()
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    mm.request_mode("manual", auth=auth)
    assert mm.is_manual
    ok, msg = mm.physical_selector("AUTO")
    assert ok
    assert mm.is_auto


def test_physical_selector_off():
    mm = PixModeManager()
    ok, msg = mm.physical_selector("OFF")
    assert ok
    assert mm.is_emergency


def test_physical_selector_unknown():
    mm = PixModeManager()
    ok, msg = mm.physical_selector("TURBO")
    assert not ok


def test_status_dict():
    mm = PixModeManager()
    s = mm.status()
    assert "mode" in s
    assert s["mode"] == "auto"
    assert "deadman_healthy" in s
    assert "safety" in s


def test_history():
    mm = PixModeManager()
    h = mm.history()
    assert isinstance(h, list)
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    mm.request_mode("manual", auth=auth, reason="test")
    h = mm.history()
    assert len(h) >= 1
    assert h[-1]["from"] == "auto"
    assert h[-1]["to"] == "manual"
    assert h[-1]["auth"] == "tech1"


def test_mode_change_callback():
    modes = []
    mm = PixModeManager()
    mm.on_mode_change = lambda m: modes.append(m.value)
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    mm.request_mode("manual", auth=auth)
    assert "manual" in modes


def test_emergency_callback():
    triggered = []
    mm = PixModeManager()
    mm.on_emergency = lambda: triggered.append(True)
    mm.request_mode("emergency")
    assert len(triggered) >= 1


def test_operator_auth_expired():
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() - 1)
    assert not auth.is_valid()


def test_operator_auth_valid():
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    assert auth.is_valid()


def test_manual_command_to_dict():
    cmd = ManualCommand(linear_vel=0.5, angular_vel=0.1, sequence=42)
    d = cmd.to_dict()
    assert d["linear_vel"] == 0.5
    assert d["angular_vel"] == 0.1
    assert d["sequence"] == 42


def test_safety_status_default():
    s = SafetyStatus()
    assert s.all_clear


def test_multiple_mode_switches():
    mm = PixModeManager()
    auth = OperatorAuth("tech1", "technician", "abc",
                        expires_at=time.monotonic() + 60)
    mm.request_mode("manual", auth=auth)
    assert mm.is_manual
    mm.request_mode("idle")
    assert mm.mode == RobotMode.IDLE
    mm.request_mode("auto")
    assert mm.is_auto


def test_deadman_switch_properties():
    ds = DeadmanSwitch(timeout=0.5)
    assert ds.timeout == 0.5
    assert not ds._armed
    ds.arm()
    assert ds._armed
    assert ds.time_since_last_signal >= 0
    ds.disarm()
    assert not ds._armed
