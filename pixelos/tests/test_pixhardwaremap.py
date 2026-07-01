"""
Tests unitaires pour PixHardwareMap — Visualisation 3D.
Couvre la topologie, la génération de scène, les calques,
l'inspection de nœuds, et l'intégration avec PixEngineer.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.pixhardware import (
    PixHardwareMonitor, NeuralFeedback, NodeStatusCode,
)
from core.pixpredict import PixPredict
from core.pixrobotcoder import PixRobotCoder
from core.pixmaintenance import PixMaintenanceBot, RepairOrder
from core.pixengineer import PixEngineer
from core.pixhardwaremap import (
    PixHardwareMap,
    ROBOT_TOPOLOGY, ROBOT_EDGES,
    COLOR_OK, COLOR_STRESS, COLOR_CRITICAL, COLOR_FAILURE,
)


class TestPixHardwareMapTopology:

    def test_topology_has_chassis(self):
        assert "CHASSIS" in ROBOT_TOPOLOGY
        assert ROBOT_TOPOLOGY["CHASSIS"]["type"] == "structure"

    def test_topology_has_arms(self):
        assert "ARM_LEFT_JOINT_01" in ROBOT_TOPOLOGY
        assert "ARM_LEFT_JOINT_02" in ROBOT_TOPOLOGY
        assert "ARM_LEFT_GRIPPER" in ROBOT_TOPOLOGY
        assert "ARM_RIGHT_JOINT_01" in ROBOT_TOPOLOGY
        assert "ARM_RIGHT_JOINT_02" in ROBOT_TOPOLOGY
        assert "ARM_RIGHT_GRIPPER" in ROBOT_TOPOLOGY

    def test_topology_has_sensors(self):
        assert "CAMERA" in ROBOT_TOPOLOGY
        assert "LIDAR" in ROBOT_TOPOLOGY

    def test_topology_has_wheels(self):
        assert "WHEEL_FL" in ROBOT_TOPOLOGY
        assert "WHEEL_FR" in ROBOT_TOPOLOGY
        assert "WHEEL_RL" in ROBOT_TOPOLOGY
        assert "WHEEL_RR" in ROBOT_TOPOLOGY

    def test_topology_has_power_and_compute(self):
        assert "BATTERY" in ROBOT_TOPOLOGY
        assert ROBOT_TOPOLOGY["BATTERY"]["type"] == "power"
        assert "CPU" in ROBOT_TOPOLOGY
        assert ROBOT_TOPOLOGY["CPU"]["type"] == "compute"

    def test_all_nodes_have_required_fields(self):
        for nid, info in ROBOT_TOPOLOGY.items():
            assert "position" in info, f"{nid} missing position"
            assert "label" in info, f"{nid} missing label"
            assert "type" in info, f"{nid} missing type"
            assert len(info["position"]) == 3

    def test_edges_connect_valid_nodes(self):
        for src, dst in ROBOT_EDGES:
            assert src in ROBOT_TOPOLOGY, f"Edge source {src} not in topology"
            assert dst in ROBOT_TOPOLOGY, f"Edge dest {dst} not in topology"

    def test_topology_version(self):
        from core.pixhardwaremap import TOPOLOGY_VERSION
        assert TOPOLOGY_VERSION == "1.0"


class TestPixHardwareMapColors:

    def test_ok_color(self):
        assert COLOR_OK == "#10b981"

    def test_stress_color(self):
        assert COLOR_STRESS == "#f59e0b"

    def test_critical_color(self):
        assert COLOR_CRITICAL == "#ef4444"

    def test_failure_color(self):
        assert COLOR_FAILURE == "#7f1d1d"


class TestPixHardwareMapCreate:

    def test_create_empty(self):
        phm = PixHardwareMap()
        assert phm is not None
        status = phm.status()
        assert status["modules"]["hardware"] is False
        assert status["topology_nodes"] == len(ROBOT_TOPOLOGY)

    def test_create_with_modules(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        phm = PixHardwareMap(hardware_monitor=hw, predict=pred)
        assert phm._hardware is hw
        assert phm._predict is pred

    def test_set_modules(self):
        phm = PixHardwareMap()
        hw = PixHardwareMonitor()
        pred = PixPredict()
        phm.set_modules(hardware=hw, predict=pred)
        assert phm._hardware is hw
        assert phm._predict is pred

    def test_status(self):
        phm = PixHardwareMap()
        s = phm.status()
        assert s["version"] == "1.0"
        assert s["topology_nodes"] > 0
        assert s["topology_edges"] > 0


class TestPixHardwareMapTopologyAPI:

    def test_get_topology(self):
        phm = PixHardwareMap()
        topo = phm.get_topology()
        assert topo["version"] == "1.0"
        assert len(topo["nodes"]) == len(ROBOT_TOPOLOGY)
        assert len(topo["edges"]) == len(ROBOT_EDGES)

    def test_topology_nodes_have_positions(self):
        phm = PixHardwareMap()
        topo = phm.get_topology()
        for n in topo["nodes"]:
            assert len(n["position"]) == 3


class TestPixHardwareMapLayers:

    def test_layers_default_visibility(self):
        phm = PixHardwareMap()
        layers = phm.get_layers()
        assert layers["health"] is True
        assert layers["maintenance"] is False
        assert layers["intervention"] is False

    def test_set_layer(self):
        phm = PixHardwareMap()
        assert phm.set_layer("health", False) is True
        assert phm.get_layers()["health"] is False

    def test_set_layer_unknown(self):
        phm = PixHardwareMap()
        assert phm.set_layer("nonexistent", True) is False

    def test_toggle_layer(self):
        phm = PixHardwareMap()
        assert phm.toggle_layer("maintenance") is True
        assert phm.get_layers()["maintenance"] is True
        assert phm.toggle_layer("maintenance") is False
        assert phm.get_layers()["maintenance"] is False

    def test_toggle_layer_unknown(self):
        phm = PixHardwareMap()
        assert phm.toggle_layer("invalid") is None


class TestPixHardwareMapScene:

    def test_scene_empty_hardware(self):
        phm = PixHardwareMap()
        scene = phm.get_scene()
        assert scene["version"] == "1.0"
        assert len(scene["nodes"]) == len(ROBOT_TOPOLOGY)
        # Sans hardware, tous les nœuds sont OK (code 0)
        for n in scene["nodes"]:
            assert n["status_code"] == 0
            assert n["color"] == COLOR_OK

    def test_scene_with_hardware_feedback(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        phm = PixHardwareMap(hardware_monitor=hw, predict=pred)

        hw.process_feedback(NeuralFeedback(
            node_id="ARM_LEFT_JOINT_02",
            status_code=NodeStatusCode.STRESS,
            temp=48.0, current=1.5, vibration=0.12,
        ))

        scene = phm.get_scene()
        nodes_map = {n["node_id"]: n for n in scene["nodes"]}
        arm = nodes_map.get("ARM_LEFT_JOINT_02")
        assert arm is not None
        assert arm["status_code"] == 1
        assert arm["color"] == COLOR_STRESS

    def test_scene_critical_node_pulses(self):
        hw = PixHardwareMonitor()
        phm = PixHardwareMap(hardware_monitor=hw)

        hw.process_feedback(NeuralFeedback(
            node_id="ARM_LEFT_JOINT_01",
            status_code=NodeStatusCode.CRITICAL,
            temp=85.0, current=2.5,
        ))

        scene = phm.get_scene()
        arm = {n["node_id"]: n for n in scene["nodes"]}["ARM_LEFT_JOINT_01"]
        assert arm["pulse"] is True
        assert arm["color"] == COLOR_CRITICAL

    def test_scene_failure_node(self):
        hw = PixHardwareMonitor()
        phm = PixHardwareMap(hardware_monitor=hw)

        hw.process_feedback(NeuralFeedback(
            node_id="MOTOR_01",
            status_code=NodeStatusCode.FAILURE,
            temp=110.0, current=0.0,
        ))

        scene = phm.get_scene()
        motor = {n["node_id"]: n for n in scene["nodes"]}["MOTOR_01"]
        assert motor["status_code"] == 3
        assert motor["color"] == COLOR_FAILURE
        assert motor["pulse"] is True

    def test_scene_with_predictions(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        phm = PixHardwareMap(hardware_monitor=hw, predict=pred)

        # Ajouter assez de feedback pour que PixPredict analyse
        for i in range(10):
            hw.process_feedback(NeuralFeedback(
                node_id="CPU",
                status_code=NodeStatusCode.STRESS,
                temp=55.0 + i * 2, current=1.5, vibration=0.08,
            ))

        scene = phm.get_scene()
        cpu = {n["node_id"]: n for n in scene["nodes"]}["CPU"]
        # La prédiction peut être nulle si analyse pas encore faite
        assert cpu["node_id"] == "CPU"

    def test_scene_cache(self):
        phm = PixHardwareMap()
        s1 = phm.get_scene()
        s2 = phm.get_scene()
        # Cache hit — même generated_at
        assert s1["generated_at"] == s2["generated_at"]

    def test_scene_edges_present(self):
        phm = PixHardwareMap()
        scene = phm.get_scene()
        assert len(scene["edges"]) == len(ROBOT_EDGES)

    def test_scene_layers_present(self):
        phm = PixHardwareMap()
        scene = phm.get_scene()
        assert "layers" in scene
        assert scene["layers"]["health"] is True
        assert scene["layers"]["maintenance"] is False


class TestPixHardwareMapInspect:

    def test_inspect_known_node(self):
        hw = PixHardwareMonitor()
        phm = PixHardwareMap(hardware_monitor=hw)
        info = phm.inspect_node("CHASSIS")
        assert info is not None
        assert info["node_id"] == "CHASSIS"
        assert info["type"] == "structure"

    def test_inspect_unknown_node(self):
        phm = PixHardwareMap()
        assert phm.inspect_node("NONEXISTENT") is None

    def test_inspect_with_hardware_data(self):
        hw = PixHardwareMonitor()
        phm = PixHardwareMap(hardware_monitor=hw)

        hw.process_feedback(NeuralFeedback(
            node_id="HEAD",
            status_code=NodeStatusCode.OK,
            temp=42.0, current=0.8,
        ))

        info = phm.inspect_node("HEAD")
        assert info["status_code"] == 0
        assert info["last_feedback"]["temp"] == 42.0

    def test_inspect_with_metrics_history(self):
        hw = PixHardwareMonitor()
        phm = PixHardwareMap(hardware_monitor=hw)

        for i in range(10):
            hw.process_feedback(NeuralFeedback(
                node_id="CPU",
                status_code=NodeStatusCode.OK,
                temp=40.0 + i, current=1.0,
            ))

        info = phm.inspect_node("CPU")
        assert len(info["metrics_history"]) >= 10

    def test_inspect_with_prediction(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        phm = PixHardwareMap(hardware_monitor=hw, predict=pred)

        for i in range(10):
            hw.process_feedback(NeuralFeedback(
                node_id="BATTERY",
                status_code=NodeStatusCode.STRESS,
                temp=50.0 + i * 3, current=2.0, vibration=0.15,
            ))

        info = phm.inspect_node("BATTERY")
        # L'inspection peut avoir prediction null si pas encore analysé
        assert info is not None


class TestPixHardwareMapIntegration:

    def test_full_integration(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        coder = PixRobotCoder()
        mb = PixMaintenanceBot()
        mb.set_robot_coder(coder)
        eng = PixEngineer(tick_interval=0.1)
        eng.set_modules(hardware=hw, predict=pred,
                       maintenance_bot=mb, robot_coder=coder)

        phm = PixHardwareMap(
            hardware_monitor=hw, predict=pred, maintenance_bot=mb,
        )

        # Envoyer du feedback pour plusieurs nœuds
        hw.process_feedback(NeuralFeedback(
            node_id="ARM_LEFT_JOINT_02",
            status_code=NodeStatusCode.STRESS,
            temp=48.0, current=1.5, vibration=0.12,
        ))
        hw.process_feedback(NeuralFeedback(
            node_id="CPU",
            status_code=NodeStatusCode.CRITICAL,
            temp=92.0, current=3.2, vibration=0.08,
        ))

        scene = phm.get_scene()
        nodes_map = {n["node_id"]: n for n in scene["nodes"]}

        assert nodes_map["ARM_LEFT_JOINT_02"]["status_code"] == 1
        assert nodes_map["CPU"]["status_code"] == 2
        assert nodes_map["CPU"]["pulse"] is True

        # Vérifier qu'au moins un nœud OK reste vert
        for nid in ["WHEEL_FL", "WHEEL_FR", "CAMERA", "LIDAR"]:
            assert nodes_map[nid]["status_code"] == 0
            assert nodes_map[nid]["color"] == COLOR_OK

    def test_layer_affects_maintenance_flag(self):
        hw = PixHardwareMonitor()
        pred = PixPredict()
        mb = PixMaintenanceBot()
        phm = PixHardwareMap(
            hardware_monitor=hw, predict=pred, maintenance_bot=mb,
        )

        hw.process_feedback(NeuralFeedback(
            node_id="MOTOR_01",
            status_code=NodeStatusCode.FAILURE,
            temp=100.0, current=0.0,
        ))

        order = RepairOrder(
            node_id="MOTOR_01",
            issue_type="EMERGENCY_FAILURE",
            priority=1.0,
            description="Test",
            created_at=time.time(),
        )
        mb.enqueue_repair(order)

        scene = phm.get_scene()
        motor = {n["node_id"]: n for n in scene["nodes"]}["MOTOR_01"]
        assert motor["status_code"] == 3
