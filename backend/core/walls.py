"""Net (usable) room dimensions — the walls stop silently eating metres.

Axis-line geometry remains the single structural model: the floor bbox IS the
building's outer face, so site placement, cost and the штамп keep their basis.
This annotation answers the other honest question — how many metres remain to
LIVE in: the exterior wall grows inward from the axis at its full geo-driven
thickness (insulation sits outside and is not subtracted), interior partitions
take half of their 120 mm on each side.

Classification is NEIGHBOUR-based, not bbox-based: an edge is exterior when
(mostly) no room lies behind it. For rectangles both definitions agree; for
the L silhouette the bbox test called the inner-corner walls facing the notch
"partitions" and under-subtracted.
"""

from core.cost_estimator import INTERIOR_WALL_T
from models import GeoClimateData, RoomLayout

_EPS = 1e-6


def _shared_frac(r: RoomLayout, wall: str, fr: list[RoomLayout]) -> float:
    """Fraction of the room's wall covered by neighbouring rooms."""
    if wall in ("S", "N"):
        edge = r.y if wall == "S" else r.y + r.depth
        spans = [
            (max(r.x, o.x), min(r.x + r.width, o.x + o.width))
            for o in fr
            if o is not r and abs((o.y + o.depth if wall == "S" else o.y) - edge) < _EPS
        ]
        length = r.width
    else:
        edge = r.x if wall == "W" else r.x + r.width
        spans = [
            (max(r.y, o.y), min(r.y + r.depth, o.y + o.depth))
            for o in fr
            if o is not r and abs((o.x + o.width if wall == "W" else o.x) - edge) < _EPS
        ]
        length = r.depth
    shared = sum(max(0.0, b - a) for a, b in spans)
    return shared / length if length > 0 else 0.0


def annotate_net_dims(rooms: list[RoomLayout], geo: GeoClimateData) -> None:
    ext_t = geo.wall_thickness_mm / 1000.0
    half_int = INTERIOR_WALL_T / 2

    for floor in {r.floor for r in rooms}:
        fr = [r for r in rooms if r.floor == floor]

        def loss(r: RoomLayout, wall: str) -> float:
            # Dominant classification: a wall mostly backed by rooms is a
            # partition, otherwise it faces outside at full thickness.
            return half_int if _shared_frac(r, wall, fr) >= 0.5 else ext_t

        for r in fr:
            loss_w = loss(r, "W") + loss(r, "E")
            loss_d = loss(r, "S") + loss(r, "N")
            r.net_width = round(max(r.width - loss_w, 0.0), 2)
            r.net_depth = round(max(r.depth - loss_d, 0.0), 2)
            r.net_area = round(r.net_width * r.net_depth, 2)
