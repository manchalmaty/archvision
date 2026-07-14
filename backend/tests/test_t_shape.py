"""T-shape (release 11): two wings and an entrance court — the roadmap's last
silhouette that can be HONEST today.

The T falls out of the wing machinery naturally: bedrooms wing over the west
corridor, garage wing over the east corridor, both corridors CONTINUING the
hallway strip — circulation correct by construction. The stem faces the
street between two entrance nooks. Its stepped wing tops run LONGER than the
bbox perimeter, so this release also flips the cost/heating exterior to the
exposed-edge sum — exact for ANY orthogonal silhouette. The true-courtyard U
stays rejected only for composer reasons now; its pricing blocker is gone.
"""

import itertools

from fastapi.testclient import TestClient

from core.cost_estimator import _floor_walls
from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine, _shared_len
from core.plan_invariants import check_invariants
from core.walls import annotate_net_dims
from main import app
from models import BuildingParams, CountryCode, RoomInput, RoomType
from tests.conftest import rooms_overlap

client = TestClient(app)
geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

T_PROGRAM = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=7),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.UTILITY, area_m2=4),
    RoomInput(room_type=RoomType.GARAGE, area_m2=22),
]


def _engine(rooms=None, **over):
    params = BuildingParams(
        rooms=rooms or T_PROGRAM,
        country=CountryCode.KZ,
        floors=over.pop("floors", 1),
        building_shape="t_shape",
        **over,
    )
    return LayoutEngine(params, geo)


def _corridors(layouts):
    halls = sorted(
        (r for r in layouts if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    assert len(halls) >= 3, "a T needs strip + two wing corridors"
    return halls[0], halls[-1]  # west, east


def test_t_is_a_real_t_with_two_nooks():
    eng = _engine()
    layouts = eng.generate()
    for a, b in itertools.combinations(layouts, 2):
        assert not rooms_overlap(a, b), f"{a.name} overlaps {b.name}"
    min_y = min(r.y for r in layouts)
    bbox_w = max(r.x + r.width for r in layouts) - min(r.x for r in layouts)
    bbox_d = max(r.y + r.depth for r in layouts) - min_y
    covered = sum(r.width * r.depth for r in layouts)
    assert covered <= 0.88 * bbox_w * bbox_d, "no real nooks — not a T"
    west, east = _corridors(layouts)
    # Both wing corridors start above street level: the nooks live below them.
    assert west.y > min_y + 0.5 and east.y > min_y + 0.5


def test_both_wings_hang_on_their_corridors():
    layouts = _engine().generate()
    west, east = _corridors(layouts)
    beds = [r for r in layouts if r.room_type == RoomType.BEDROOM]
    garage = next(r for r in layouts if r.room_type == RoomType.GARAGE)
    assert all(_shared_len(b, west) > 0.7 for b in beds), "bedrooms off west corridor"
    assert _shared_len(garage, east) > 0.7, "garage off east corridor"


def test_invariants_clean_and_no_rule10():
    eng = _engine()
    layouts = eng.generate()
    annotate_net_dims(layouts, geo)
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    assert v == [], [f"rule {x.rule} {x.code}: {x.message}" for x in v]


def test_t_perimeter_priced_true():
    # A stepped T runs LONGER than its bbox (the wing tops break monotonicity)
    # — the cost model now bills the exposed-edge sum, not the bbox shortcut.
    layouts = _engine().generate()
    ext_model, _ = _floor_walls(layouts)

    def exposed(r, wall):
        if wall in ("S", "N"):
            edge = r.y if wall == "S" else r.y + r.depth
            spans = [
                (max(r.x, o.x), min(r.x + r.width, o.x + o.width))
                for o in layouts
                if o is not r
                and abs((o.y + o.depth if wall == "S" else o.y) - edge) < 1e-6
            ]
            length = r.width
        else:
            edge = r.x if wall == "W" else r.x + r.width
            spans = [
                (max(r.y, o.y), min(r.y + r.depth, o.y + o.depth))
                for o in layouts
                if o is not r
                and abs((o.x + o.width if wall == "W" else o.x) - edge) < 1e-6
            ]
            length = r.depth
        return max(0.0, length - sum(max(0.0, b - a) for a, b in spans))

    true_perimeter = sum(exposed(r, w) for r in layouts for w in ("S", "N", "W", "E"))
    assert abs(true_perimeter - ext_model) < 0.05, "cost must bill the true exterior"
    bbox_perimeter = 2 * (
        (max(r.x + r.width for r in layouts) - min(r.x for r in layouts))
        + (max(r.y + r.depth for r in layouts) - min(r.y for r in layouts))
    )
    assert ext_model >= bbox_perimeter - 0.05  # re-entrant walls never under-billed


def test_entrance_lands_on_an_exterior_wall():
    layouts = _engine().generate()
    halls = [r for r in layouts if r.room_type == RoomType.HALLWAY]
    doored = [r for r in halls if r.doors]
    assert doored, "circulation carries the entrance"
    # At least one hallway door sits on a wall no room backs — the real entry.
    def has_exterior_door(r):
        for d in r.doors:
            others = [o for o in layouts if o is not r]
            if d.wall == "S" and not any(
                abs(o.y + o.depth - r.y) < 1e-6 and o.x < r.x + r.width and o.x + o.width > r.x
                for o in others
            ):
                return True
        return False
    assert any(has_exterior_door(r) for r in halls), "entrance must reach outside"


def test_fallback_cascade():
    # No garage/utility → the T degrades to the bedroom-wing L.
    no_wing2 = [r for r in T_PROGRAM if r.room_type not in (RoomType.GARAGE, RoomType.UTILITY)]
    eng = _engine(rooms=no_wing2)
    layouts = eng.generate()
    assert any("T" in w for w in eng.warnings)
    halls = [r for r in layouts if r.room_type == RoomType.HALLWAY]
    assert len(halls) == 2  # strip + ONE wing corridor = the L
    # Two floors → the two-storey Г takes over.
    eng2 = _engine(floors=2)
    layouts2 = eng2.generate()
    assert any("T" in w for w in eng2.warnings)
    assert any(r.floor == 2 for r in layouts2)


def test_u_shape_still_rejected():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [{"room_type": "bedroom", "area_m2": 15}],
            "country": "KZ",
            "floors": 1,
            "building_shape": "u_shape",
        },
    )
    assert r.status_code == 422
