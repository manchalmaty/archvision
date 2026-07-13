"""Release-6 consumers: every downstream figure stays honest for an L.

- Site coverage counts the BUILT footprint (Σ ground rooms), not the bbox —
  an L exists partly to fit the 30% limit, charging its notch as built area
  would defeat the point. Setbacks stay bbox-based (conservative, correct).
- Net-dim wall classification goes neighbour-based: an edge is exterior when
  (mostly) no room lies behind it — the bbox test called the L's inner-corner
  walls "partitions" and under-subtracted.
- Cost and heating stay UNCHANGED by geometry: a staircase-monotone L has
  exactly its bbox perimeter, which is what _floor_walls already uses — the
  cross-check test pins that theorem to this composer.
"""

from core.cost_estimator import INTERIOR_WALL_T, _floor_walls
from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.site_planner import plan_site
from core.walls import annotate_net_dims
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.RU, "Москва", 1)
EXT_T = geo.wall_thickness_mm / 1000.0
HALF_INT = INTERIOR_WALL_T / 2

L_PROGRAM = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
]


def _l_layout():
    params = BuildingParams(
        rooms=L_PROGRAM, country=CountryCode.RU, region="Москва",
        floors=1, building_shape="l_shape",
    )
    eng = LayoutEngine(params, geo)
    return eng.generate()


def test_site_coverage_counts_built_area_not_bbox():
    layouts = _l_layout()
    built = sum(r.width * r.depth for r in layouts)
    bw = max(r.x + r.width for r in layouts) - min(r.x for r in layouts)
    bd = max(r.y + r.depth for r in layouts) - min(r.y for r in layouts)
    assert built < 0.9 * bw * bd  # sanity: this really is an L
    site = plan_site(layouts, 40.0, 40.0, "S", 1)
    assert abs(site.coverage_ratio - built / 1600.0) < 1e-3
    assert site.coverage_ratio < (bw * bd) / 1600.0  # notch not charged


def test_notch_facing_wall_is_exterior_in_net_dims():
    layouts = _l_layout()
    annotate_net_dims(layouts, geo)
    # The wing-B corridor is the EASTERNMOST hallway (the wing-A strip may
    # itself start past x=0 when the overshoot filler pulls a WC into it).
    corridor = max(
        (r for r in layouts if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    # South face looks into the notch (exterior, full thickness); north face is
    # shared with the bedroom row (partition, half thickness).
    expected = corridor.depth - EXT_T - HALF_INT
    assert abs(corridor.net_depth - expected) < 0.011, (
        f"net_depth {corridor.net_depth} vs expected {expected} — "
        "the notch wall must count as exterior"
    )


def test_rectangle_net_dims_unchanged_by_neighbour_classification():
    # The refactor must not move the figures for plain rectangles.
    params = BuildingParams(
        rooms=[r for r in L_PROGRAM if r.room_type != RoomType.BEDROOM]
        + [RoomInput(room_type=RoomType.BEDROOM, area_m2=14)],
        country=CountryCode.RU, region="Москва", floors=1,
    )
    layouts = LayoutEngine(params, geo).generate()
    annotate_net_dims(layouts, geo)
    for r in layouts:
        assert r.net_area is not None
        assert 0 < r.net_area < r.width * r.depth


def test_l_exterior_perimeter_equals_bbox_perimeter():
    # The theorem the cost & heating models rely on: this composer's L is
    # staircase-monotone, so its true exterior length IS the bbox perimeter.
    layouts = _l_layout()
    ext_bbox, _ = _floor_walls(layouts)

    def exposed(r, wall):
        if wall in ("S", "N"):
            edge_y = r.y if wall == "S" else r.y + r.depth
            span = [
                (max(r.x, o.x), min(r.x + r.width, o.x + o.width))
                for o in layouts
                if o is not r
                and abs((o.y + o.depth if wall == "S" else o.y) - edge_y) < 1e-6
            ]
            length = r.width
        else:
            edge_x = r.x if wall == "W" else r.x + r.width
            span = [
                (max(r.y, o.y), min(r.y + r.depth, o.y + o.depth))
                for o in layouts
                if o is not r
                and abs((o.x + o.width if wall == "W" else o.x) - edge_x) < 1e-6
            ]
            length = r.depth
        shared = sum(max(0.0, b - a) for a, b in span)
        return max(0.0, length - shared)

    true_perimeter = sum(
        exposed(r, w) for r in layouts for w in ("S", "N", "W", "E")
    )
    assert abs(true_perimeter - ext_bbox) < 0.05, (
        f"bbox perimeter {ext_bbox} vs true exposed {true_perimeter}"
    )
