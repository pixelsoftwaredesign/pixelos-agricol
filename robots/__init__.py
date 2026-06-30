from .base import RobotNode, RobotMission, MISSION_STATUS
from .inspecteur import RobotInspecteur
from .transporteur import RobotTransporteur
from .recolteur import RobotRecolteur

ROBOT_ROLES = {
    "inspecteur": RobotInspecteur,
    "transporteur": RobotTransporteur,
    "recolteur": RobotRecolteur,
}

def create_robot(role: str, name: str = "") -> RobotNode:
    cls = ROBOT_ROLES.get(role)
    if not cls:
        raise ValueError(f"Unknown robot role: {role}. Choices: {list(ROBOT_ROLES.keys())}")
    return cls(name or f"{role}-{hash(role) & 0xffff:04x}")
