"""Real L-shape (release 6): the first honest non-rectangle.

Wing A = the proven central-hall bar (social + wet core + garage). Wing B =
the bedroom bar, whose corridor CONTINUES the hallway strip through the seam —
circulation lives at the joint by construction, which is exactly what the old
wing layouts got wrong (hallway stranded in a corner → transit through a
toilet). The missing south band of wing B is the notch: a street-facing
courtyard nook. Rule 1's coverage denominator becomes the declared silhouette,
not the bbox — an L covers its own outline, not its bounding box.

v1 scope, honest: one floor only, needs ≥2 bedrooms; anything else warns and
falls back to the rectangle. U/T stay out until they truly tile.
"""

import itertools

from fastapi.testclient import TestClient

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from main import app
from models import BuildingParams, CountryCode, RoomInput, RoomType
from tests.conftest import rooms_overlap

client = TestClient(app)
geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

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


def _engine(rooms=None, **over) -> LayoutEngine:
    params = BuildingParams(
        rooms=rooms or L_PROGRAM,
        country=CountryCode.KZ,
        floors=over.pop("floors", 1),
        building_shape="l_shape",
        **over,
    )
    return LayoutEngine(params, geo)


def test_l_is_a_real_l_with_a_notch():
    eng = _engine()
    layouts = eng.generate()
    min_x, min_y = min(r.x for r in layouts), min(r.y for r in layouts)
    bbox = (max(r.x + r.width for r in layouts) - min_x) * (
        max(r.y + r.depth for r in layouts) - min_y
    )
    covered = sum(r.width * r.depth for r in layouts)
    assert covered <= 0.88 * bbox, "no real notch — this is still a rectangle"
    for a, b in itertools.combinations(layouts, 2):
        assert not rooms_overlap(a, b), f"{a.name} overlaps {b.name}"
    # The declared silhouette must be what the rooms actually tile.
    assert eng.silhouette_m2 is not None
    assert covered >= 0.9 * eng.silhouette_m2


def test_circulation_lives_at_the_joint():
    layouts = _engine().generate()
    halls = [r for r in layouts if r.room_type == RoomType.HALLWAY]
    assert len(halls) >= 2, "wing B must carry its corridor"
    # Every bedroom is served directly from a hallway cell (the old failure
    # was bedrooms reachable only through other rooms).
    from core.layout_engine import _shared_len

    for bed in (r for r in layouts if r.room_type == RoomType.BEDROOM):
        assert any(_shared_len(bed, h) > 0.7 for h in halls), f"{bed.name} off-corridor"


def test_invariants_clean_with_silhouette():
    eng = _engine()
    layouts = eng.generate()
    violations = check_invariants(layouts, openness="closed", silhouette_m2=eng.silhouette_m2)
    assert violations == [], [f"rule {v.rule} {v.code}: {v.message}" for v in violations]


def test_bbox_denominator_would_cry_wolf():
    # Pins WHY silhouette_m2 exists: judged against the bbox, a healthy L
    # reads as a floor full of gaps.
    eng = _engine()
    layouts = eng.generate()
    legacy = check_invariants(layouts, openness="closed")
    assert any(v.rule == 1 and v.code == "gap" for v in legacy)


def test_one_bedroom_falls_back_to_rectangle_with_warning():
    program = [r for r in L_PROGRAM if r.room_type != RoomType.BEDROOM] + [
        RoomInput(room_type=RoomType.BEDROOM, area_m2=14)
    ]
    eng = _engine(rooms=program)
    layouts = eng.generate()
    min_x, min_y = min(r.x for r in layouts), min(r.y for r in layouts)
    bbox = (max(r.x + r.width for r in layouts) - min_x) * (
        max(r.y + r.depth for r in layouts) - min_y
    )
    assert sum(r.width * r.depth for r in layouts) >= 0.9 * bbox  # rectangle again
    assert any("L" in w for w in eng.warnings)


def test_two_floors_fall_back_with_warning():
    eng = _engine(floors=2)
    eng.generate()
    assert any("L" in w for w in eng.warnings)


def test_garage_rides_in_wing_a():
    program = L_PROGRAM + [RoomInput(room_type=RoomType.GARAGE, area_m2=22)]
    eng = _engine(rooms=program)
    layouts = eng.generate()
    violations = check_invariants(layouts, openness="closed", silhouette_m2=eng.silhouette_m2)
    errors = [v for v in violations if v.severity == "ERROR"]
    assert errors == [], [f"rule {v.rule}: {v.message}" for v in errors]


def test_api_accepts_l_shape_and_ships_no_false_gap():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [
                {"room_type": ri.room_type.value, "area_m2": ri.area_m2} for ri in L_PROGRAM
            ],
            "country": "KZ",
            "floors": 1,
            "building_shape": "l_shape",
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    inv_errors = [i for i in body["compliance_issues"] if i["rule_id"].startswith("INV-")]
    assert [i for i in inv_errors if "INV-1-" in i["rule_id"]] == [], inv_errors
    assert inv_errors == [], inv_errors
