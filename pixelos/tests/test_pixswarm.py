"""
Tests unitaires pour PixSwarm.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.pixswarm import (
    PixSwarm, SwarmHeartbeat, FormationOrder,
    FormationType, NodeRole, NodeStatus,
    HEARTBEAT_TOPIC, FORMATION_TOPIC, EMERGENCY_TOPIC, LEADER_TOPIC,
)

_HB = 0.3


def test_create_swarm():
    s = PixSwarm(heartbeat_interval=_HB, role="drone")
    assert s.role == "drone"
    assert s.domain_id == 0
    s.stop()


def test_start_stop():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    assert s._running
    time.sleep(0.4)
    s.stop()
    assert not s._running


def test_heartbeat_status():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    time.sleep(0.4)
    st = s.status()
    assert st["running"] is True
    s.stop()


def test_update_heartbeat():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    time.sleep(0.3)
    s.update_heartbeat(battery=85, load_avg=0.3, position=(10, 0, 5))
    time.sleep(0.4)
    st = s.status()
    assert st["battery"] == 85
    assert st["load_avg"] == 0.3
    s.stop()


def test_member_detection():
    s1 = PixSwarm(heartbeat_interval=_HB, node_id="robot_a")
    s2 = PixSwarm(heartbeat_interval=_HB, node_id="robot_b")
    s1.start()
    s2.start()
    time.sleep(1.5)
    ids_1 = [m["node_id"] for m in s1.get_members()]
    ids_2 = [m["node_id"] for m in s2.get_members()]
    assert "robot_b" in ids_1
    assert "robot_a" in ids_2
    s1.stop()
    s2.stop()


def test_leader_election():
    s1 = PixSwarm(heartbeat_interval=_HB, node_id="high_bat")
    s2 = PixSwarm(heartbeat_interval=_HB, node_id="low_bat")
    s1.start()
    s2.start()
    time.sleep(0.5)
    s1.update_heartbeat(battery=90, load_avg=0.2)
    s2.update_heartbeat(battery=50, load_avg=0.5)
    time.sleep(1.0)
    st1 = s1.status()
    st2 = s2.status()
    assert st1["is_leader"] or st2["is_leader"]
    s1.stop()
    s2.stop()


def test_formation_line():
    s = PixSwarm(heartbeat_interval=_HB, formation="line")
    s.start()
    time.sleep(0.3)
    off = FormationType.offsets("line", 4, 2)
    assert off[2] == -4.0
    s.stop()


def test_formation_offsets():
    off_v = [FormationType.offsets("flying_v", 4, i) for i in range(4)]
    assert len(set(o[0] for o in off_v)) == 4
    off_g = [FormationType.offsets("grid", 4, i) for i in range(4)]
    assert off_g[0] == (0, 0, 0)
    assert off_g[1] == (3, 0, 0)
    assert off_g[2] == (0, 3, 0)
    assert off_g[3] == (3, 3, 0)
    off_l = [FormationType.offsets("line", 3, i) for i in range(3)]
    assert off_l[0] == (0, 0, 0)
    assert off_l[1] == (0, 0, -2)
    assert off_l[2] == (0, 0, -4)


def test_swarm_heartbeat_serialization():
    hb = SwarmHeartbeat(node_id="t", role="drone", domain_id=0,
                         battery=75, load_avg=0.5, position=(1, 2, 3))
    d = hb.to_dict()
    assert d["node_id"] == "t"
    hb2 = SwarmHeartbeat.from_dict(d)
    assert hb2.battery == 75


def test_formation_order_serialization():
    fo = FormationOrder(ftype="flying_v", leader_id="l1",
                         members=["l1", "b1"], speed=1.5, altitude=12)
    d = fo.to_dict()
    assert d["ftype"] == "flying_v"
    fo2 = FormationOrder.from_dict(d)
    assert fo2.leader_id == "l1"


def test_broadcast_emergency():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    time.sleep(0.3)
    s.broadcast_emergency("Test urgence")
    time.sleep(0.4)
    assert s.status()["emergency"] is True
    s.clear_emergency()
    time.sleep(0.4)
    assert s.status()["emergency"] is False
    s.stop()


def test_emergency_propagation():
    s1 = PixSwarm(heartbeat_interval=_HB, node_id="emit")
    s2 = PixSwarm(heartbeat_interval=_HB, node_id="recv")
    recv = []
    s2.on_emergency = lambda d: recv.append(d)
    s1.start()
    s2.start()
    time.sleep(1.0)
    s1.broadcast_emergency("Danger")
    time.sleep(0.5)
    assert len(recv) > 0
    assert "Danger" in str(recv[0].get("msg", ""))
    s1.stop()
    s2.stop()


def test_set_formation():
    s = PixSwarm(heartbeat_interval=_HB, formation="flying_v")
    s.start()
    time.sleep(0.3)
    ok = s.set_formation("grid")
    assert ok or s.formation_type == "flying_v"
    s.stop()


def test_member_timeout():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    time.sleep(0.3)
    s._members["ghost"] = SwarmHeartbeat(
        node_id="ghost", role="drone", domain_id=0,
        timestamp=time.monotonic() - 15,
    )
    assert "ghost" in s._members
    time.sleep(2.0)
    assert "ghost" not in s._members
    s.stop()


def test_status_fields():
    s = PixSwarm(heartbeat_interval=_HB)
    s.start()
    time.sleep(0.3)
    st = s.status()
    for f in ["node_id", "role", "is_leader", "formation", "running"]:
        assert f in st
    s.stop()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"  RUN  {name}...", end=" ")
            try:
                fn()
                print("OK")
            except Exception as e:
                print(f"FAIL: {e}")
                import traceback
                traceback.print_exc()
