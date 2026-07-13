"""Rule 9 on CLEAR dimensions (release 9) — the last axis holdout falls.

Since v1.6 every area is usable metres, but minimum dimensions were still
judged on axis lines: a 0.9 m axis toilet against a 380 mm wall is 0.46 m
clear — furniture physics, silently ignored. Now the engine pads its sizing
minimums by the wall losses (uniform conservative pad = exterior thickness +
half a partition, so corner cells are covered too), and rule 9 judges the net
figures with the usual axis fallback for un-annotated callers.
"""

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import USABLE_MIN_SIDE, LayoutEngine
from core.plan_invariants import check_invariants
from core.walls import annotate_net_dims
from models import BuildingParams, CountryCode, RoomInput, RoomLayout, RoomType

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


def _layouts(rooms=None, **over):
    params = BuildingParams(
        rooms=rooms or PROGRAM, country=CountryCode.KZ, floors=1, **over
    )
    eng = LayoutEngine(params, geo)
    out = eng.generate()
    annotate_net_dims(out, geo)
    return out, eng


def test_rule9_judges_clear_dimension():
    room = RoomLayout(
        room_id="a", room_type=RoomType.BEDROOM, name="Bedroom", x=0, y=0,
        floor=1, width=2.5, depth=4.0, area_m2=10.0,
        doors=[{"wall": "S", "position": 1.0}],
        net_width=2.06, net_depth=3.56, net_area=7.33,  # corner + thick walls
    )
    v = check_invariants([room])
    assert any(x.rule == 9 for x in v), "2.06 m clear must flag for a bedroom"
    room2 = room.model_copy(update={"net_width": None, "net_depth": None, "net_area": None})
    assert not any(x.rule == 9 for x in check_invariants([room2]))  # axis fallback


def test_every_room_clears_its_minimum_in_the_clear():
    layouts, eng = _layouts()
    for r in layouts:
        min_side = USABLE_MIN_SIDE.get(r.room_type, 1.5)
        assert min(r.net_width, r.net_depth) >= min_side - 0.01, (
            f"{r.name}: {r.net_width}×{r.net_depth} clear vs min {min_side}"
        )


def test_garage_fits_a_car_in_the_clear():
    layouts, _ = _layouts(rooms=PROGRAM + [RoomInput(room_type=RoomType.GARAGE, area_m2=22)])
    garage = next(r for r in layouts if r.room_type == RoomType.GARAGE)
    assert min(garage.net_width, garage.net_depth) >= 3.0 - 0.01, (
        f"garage {garage.net_width}×{garage.net_depth} clear — the car does not fit"
    )


def test_l_corridor_clears_net_minimum():
    program = PROGRAM + [RoomInput(room_type=RoomType.BEDROOM, area_m2=12)]
    layouts, eng = _layouts(rooms=program, building_shape="l_shape")
    corridor = max(
        (r for r in layouts if r.room_type == RoomType.HALLWAY), key=lambda r: r.x
    )
    assert corridor.net_depth >= USABLE_MIN_SIDE[RoomType.HALLWAY] - 0.01
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    assert not any(x.rule == 9 for x in v), [x.message for x in v if x.rule == 9]


def test_full_program_ships_no_rule9_red():
    layouts, eng = _layouts(rooms=PROGRAM + [RoomInput(room_type=RoomType.GARAGE, area_m2=22)])
    v = check_invariants(layouts, silhouette_m2=eng.silhouette_m2)
    assert not any(x.rule == 9 for x in v), [x.message for x in v if x.rule == 9]
