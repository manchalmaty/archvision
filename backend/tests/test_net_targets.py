"""Net-target sizing (release 7): «12 м²» now means 12 m² to LIVE in.

The engine tiles a draft, measures what the walls actually eat at each room's
position, grosses the axis targets per room and retiles — two fixed passes,
deterministic. `area_m2` keeps the USER's request, so invariant rule 2 can
honestly judge usable-vs-requested. Hallways are exempt from rule 2 (they
print their real figure by design); rule 9 (min dimension) intentionally
stays axis-based until corner-aware band sizing lands — documented, not
hidden.
"""

from fastapi.testclient import TestClient

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from core.walls import annotate_net_dims
from main import app
from models import BuildingParams, CountryCode, RoomInput, RoomLayout, RoomType

client = TestClient(app)
geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

PROGRAM = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
]

HABITABLE = {RoomType.LIVING_ROOM, RoomType.BEDROOM, RoomType.KITCHEN}


def _generate(rooms=None, **over):
    params = BuildingParams(
        rooms=rooms or PROGRAM, country=CountryCode.KZ, floors=over.pop("floors", 1), **over
    )
    eng = LayoutEngine(params, geo)
    layouts = eng.generate()
    annotate_net_dims(layouts, geo)
    return layouts


def test_habitable_net_area_lands_on_the_request():
    layouts = _generate()
    for r in layouts:
        if r.room_type in HABITABLE:
            assert r.net_area >= 0.9 * r.area_m2, (
                f"{r.name}: net {r.net_area} vs request {r.area_m2} — "
                "the walls still eat the request"
            )
            # ...and the axis honestly grew to pay for the walls.
            assert r.width * r.depth > r.area_m2


def test_area_m2_still_prints_the_request():
    layouts = _generate()
    requested = sorted(ri.area_m2 for ri in PROGRAM)
    got = sorted(r.area_m2 for r in layouts if any(
        ri.room_type == r.room_type for ri in PROGRAM
    ))
    assert got == requested, f"{got} != {requested} — grossed targets leaked into area_m2"


def test_garage_delivers_clear_parking_metres():
    layouts = _generate(rooms=PROGRAM + [RoomInput(room_type=RoomType.GARAGE, area_m2=22)])
    garage = next(r for r in layouts if r.room_type == RoomType.GARAGE)
    assert garage.area_m2 == 22.0  # the printed request is the user's figure
    assert garage.net_area >= 0.9 * 22.0  # ...and the clear metres deliver it


def test_two_passes_are_deterministic():
    a = [(r.room_type, r.x, r.y, r.width, r.depth) for r in _generate()]
    b = [(r.room_type, r.x, r.y, r.width, r.depth) for r in _generate()]
    assert a == b


def test_rule2_judges_net_when_annotated():
    room = RoomLayout(
        room_id="a", room_type=RoomType.BEDROOM, name="Bedroom", x=0, y=0,
        floor=1, width=4, depth=3, area_m2=12.0,
        doors=[{"wall": "S", "position": 1.0}],
        net_width=3.5, net_depth=2.6, net_area=9.1,  # walls ate a quarter
    )
    v = check_invariants([room])
    assert any(x.rule == 2 for x in v), "rule 2 must judge usable metres"
    # Same geometry, no net annotation → legacy axis judgement, no flag.
    room2 = room.model_copy(update={"net_width": None, "net_depth": None, "net_area": None})
    assert not any(x.rule == 2 for x in check_invariants([room2]))


def test_hallway_exempt_from_rule2():
    hall = RoomLayout(
        room_id="h", room_type=RoomType.HALLWAY, name="Hallway", x=0, y=0,
        floor=1, width=10, depth=1.3, area_m2=13.0,
        doors=[{"wall": "S", "position": 1.0}],
        net_width=9.9, net_depth=0.86, net_area=8.5,  # corridors lose a lot
    )
    assert not any(x.rule == 2 for x in check_invariants([hall]))


def test_l_shape_stays_rule2_clean():
    program = PROGRAM + [RoomInput(room_type=RoomType.BEDROOM, area_m2=12)]
    params = BuildingParams(
        rooms=program, country=CountryCode.KZ, floors=1, building_shape="l_shape"
    )
    eng = LayoutEngine(params, geo)
    layouts = eng.generate()
    annotate_net_dims(layouts, geo)
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    assert not any(x.rule == 2 for x in v), [x.message for x in v if x.rule == 2]


def test_api_ships_request_figures_and_no_rule2_red():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [
                {"room_type": ri.room_type.value, "area_m2": ri.area_m2} for ri in PROGRAM
            ],
            "country": "KZ",
            "floors": 1,
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert not [i for i in body["compliance_issues"] if i["rule_id"].startswith("INV-2")]
    for room in body["rooms"]:
        if room["room_type"] in ("living_room", "bedroom", "kitchen"):
            assert room["net_area"] >= 0.9 * room["area_m2"]
