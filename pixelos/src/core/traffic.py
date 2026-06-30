"""
PixTraffic — Code de la Route PixelOS.

Hiérarchie des priorités entre robots et règles de droit de passage.
Utilisé par le TrafficController (orchestrateur) et localement par chaque robot.
"""

from enum import IntEnum


class Priority(IntEnum):
    RECOLTEUR = 2
    TRANSPORT = 5
    INSPECTEUR = 10


ROLE_PRIORITY = {
    "RECOLTEUR": Priority.RECOLTEUR,
    "TRANSPORT": Priority.TRANSPORT,
    "TRANSPORTEUR": Priority.TRANSPORT,
    "INSPECTEUR": Priority.INSPECTEUR,
    "DRONE": Priority.INSPECTEUR,
}


class RightOfWay:
    """Évalue les droits de priorité entre deux robots."""

    @staticmethod
    def has_priority(role_a: str, role_b: str) -> bool:
        return ROLE_PRIORITY.get(role_a.upper(), 0) >= ROLE_PRIORITY.get(role_b.upper(), 0)

    @staticmethod
    def can_proceed(self_role: str, other_role: str) -> bool:
        """True si self peut avancer sans conflit avec other."""
        return ROLE_PRIORITY.get(self_role.upper(), 0) > ROLE_PRIORITY.get(other_role.upper(), 0)

    @staticmethod
    def must_yield(self_role: str, other_role: str) -> bool:
        """True si self doit céder le passage à other."""
        return ROLE_PRIORITY.get(self_role.upper(), 0) < ROLE_PRIORITY.get(other_role.upper(), 0)

    @staticmethod
    def overlap_zones(zone_a: tuple, zone_b: tuple) -> bool:
        """Vérifie si deux zones de travail (x1,y1,x2,y2) se chevauchent."""
        ax1, ay1, ax2, ay2 = zone_a
        bx1, by1, bx2, by2 = zone_b
        return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1

    @staticmethod
    def collision_risk(pos_a: tuple, pos_b: tuple, threshold: float = 2.0) -> bool:
        """Distance < threshold → risque de collision."""
        dx = pos_a[0] - pos_b[0]
        dy = pos_a[1] - pos_b[1]
        return (dx * dx + dy * dy) ** 0.5 < threshold


# ── Commandes de trafic standardisées ─────────────────────

TRAFFIC_CMD_STOP = "TRAFFIC_STOP"
TRAFFIC_CMD_RESUME = "TRAFFIC_RESUME"
TRAFFIC_CMD_YIELD = "TRAFFIC_YIELD"
TRAFFIC_CMD_OVERRIDE = "TRAFFIC_OVERRIDE"
TRAFFIC_CMD_HOLD_POSITION = "TRAFFIC_HOLD"
TRAFFIC_CMD_CLEAR_ZONE = "TRAFFIC_CLEAR"
