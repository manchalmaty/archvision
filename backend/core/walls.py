"""Net (usable) room dimensions — the walls stop silently eating metres.

Axis-line geometry remains the single structural model: the floor bbox IS the
building's outer face, so site placement, cost and the штамп keep their basis.
This annotation answers the other honest question — how many metres remain to
LIVE in: the exterior wall grows inward from the axis at its full geo-driven
thickness (insulation sits outside and is not subtracted), interior partitions
take half of their 120 mm on each side. A room edge lying on its floor's bbox
is exterior; everything else is a partition.
"""

from core.cost_estimator import INTERIOR_WALL_T
from models import GeoClimateData, RoomLayout

_EPS = 1e-6


def annotate_net_dims(rooms: list[RoomLayout], geo: GeoClimateData) -> None:
    ext_t = geo.wall_thickness_mm / 1000.0
    half_int = INTERIOR_WALL_T / 2

    for floor in {r.floor for r in rooms}:
        fr = [r for r in rooms if r.floor == floor]
        min_x = min(r.x for r in fr)
        min_y = min(r.y for r in fr)
        max_x = max(r.x + r.width for r in fr)
        max_y = max(r.y + r.depth for r in fr)

        for r in fr:
            loss_w = (ext_t if abs(r.x - min_x) < _EPS else half_int) + (
                ext_t if abs(r.x + r.width - max_x) < _EPS else half_int
            )
            loss_d = (ext_t if abs(r.y - min_y) < _EPS else half_int) + (
                ext_t if abs(r.y + r.depth - max_y) < _EPS else half_int
            )
            r.net_width = round(max(r.width - loss_w, 0.0), 2)
            r.net_depth = round(max(r.depth - loss_d, 0.0), 2)
            r.net_area = round(r.net_width * r.net_depth, 2)
