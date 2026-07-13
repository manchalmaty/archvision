"""Multi-floor L (release 10): the classic two-storey Г-дом.

Ground floor = wing A (social + wet core) + a GARAGE wing over the corridor
continuation — the person-door enters through the corridor (a true hallway
buffer, rule 10 clean), the gate faces the notch courtyard, which IS the
driveway. Upper floors = a bedroom rectangle pinned to wing A's width (an
upper floor wider than the bar it stands on is structural fiction).
Silhouette becomes per-floor: rule 1 judges each floor by its own outline.
"""

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from core.walls import annotate_net_dims
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 2)

PROGRAM = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=22),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=11),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=7),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=15),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=13),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.UTILITY, area_m2=4),
    RoomInput(room_type=RoomType.GARAGE, area_m2=22),
]


def _engine(rooms=None, **over):
    params = BuildingParams(
        rooms=rooms or PROGRAM,
        country=CountryCode.KZ,
        floors=over.pop("floors", 2),
        building_shape="l_shape",
        **over,
    )
    return LayoutEngine(params, geo)


def test_ground_floor_is_an_l_with_the_garage_in_the_wing():
    eng = _engine()
    layouts = eng.generate()
    ground = [r for r in layouts if r.floor == 1]
    bbox = (
        max(r.x + r.width for r in ground) - min(r.x for r in ground)
    ) * (max(r.y + r.depth for r in ground) - min(r.y for r in ground))
    covered = sum(r.width * r.depth for r in ground)
    assert covered <= 0.88 * bbox, "ground floor must carry a real notch"
    garage = next(r for r in ground if r.room_type == RoomType.GARAGE)
    corridor = max(
        (r for r in ground if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    # The garage lives in wing B, east of the seam, over the corridor.
    assert garage.x >= corridor.x - 1e-6
    from core.layout_engine import _shared_len

    assert _shared_len(garage, corridor) > 0.7, "garage must sit on its buffer corridor"


def test_upper_floor_stays_on_wing_a():
    eng = _engine()
    layouts = eng.generate()
    ground = [r for r in layouts if r.floor == 1]
    # The seam = where the wing-B corridor starts; wing A spans [0, seam].
    corridor = max(
        (r for r in ground if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    w1 = corridor.x
    upper = [r for r in layouts if r.floor == 2]
    assert upper, "bedrooms must land upstairs"
    assert all(r.room_type in (RoomType.BEDROOM, RoomType.HALLWAY) for r in upper)
    upper_w = max(r.x + r.width for r in upper)
    assert upper_w <= w1 + 0.02, f"upper floor {upper_w} overhangs wing A {w1}"


def test_two_floor_l_passes_all_invariants():
    eng = _engine()
    layouts = eng.generate()
    annotate_net_dims(layouts, geo)
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    assert v == [], [f"rule {x.rule} {x.code}: {x.message}" for x in v]


def test_garage_person_door_enters_through_the_corridor():
    eng = _engine()
    layouts = eng.generate()
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    # A hallway buffer at the garage door means rule 10 has nothing to say.
    assert not any(x.rule == 10 for x in v)


def test_no_wing_occupant_falls_back_with_warning():
    program = [r for r in PROGRAM if r.room_type not in (RoomType.GARAGE, RoomType.UTILITY)]
    eng = _engine(rooms=program)
    layouts = eng.generate()
    ground = [r for r in layouts if r.floor == 1]
    bbox = (
        max(r.x + r.width for r in ground) - min(r.x for r in ground)
    ) * (max(r.y + r.depth for r in ground) - min(r.y for r in ground))
    assert sum(r.width * r.depth for r in ground) >= 0.9 * bbox  # rectangle again
    assert any("L" in w for w in eng.warnings)


def test_single_floor_l_unchanged():
    eng = _engine(floors=1)
    layouts = eng.generate()
    # bedrooms stay the wing on one floor (the release-6 contract)
    corridor = max(
        (r for r in layouts if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    beds_in_wing = [
        r for r in layouts if r.room_type == RoomType.BEDROOM and r.x >= corridor.x - 1e-6
    ]
    assert len(beds_in_wing) >= 2
