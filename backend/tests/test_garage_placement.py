"""Garage is PLACED next to circulation, not just doored well after the fact.

The prior fix chose the garage door well and flagged bad ones (rule 10), but the
LAYOUT still stranded the garage against the wet/private band: on no-utility
presets in open/mixed the garage bordered only bath/toilet/bedroom, so the honest
outcome was an ERROR. This adds a placement constraint — a narrow hallway
"tambour" cell carved into the garage-adjacent band — so the garage opens into a
real buffer. Where the tambour cannot fit, the garage may fall back to the
kitchen, which is now an honest rule-10 WARNING (allowed, not ideal), never a
silent green.
"""

import pytest

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine, _door_target
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)
R = RoomType

TRUE_BUFFER = {R.HALLWAY, R.UTILITY}
SOFT_BUFFER = {R.KITCHEN, R.LIVING_ROOM}
FORBIDDEN = {R.BATHROOM, R.TOILET, R.BEDROOM}

PRESETS = {
    "single": [(R.LIVING_ROOM, 18), (R.BEDROOM, 12), (R.KITCHEN, 9), (R.BATHROOM, 4), (R.HALLWAY, 5)],
    "couple": [(R.LIVING_ROOM, 20), (R.BEDROOM, 14), (R.KITCHEN, 10), (R.BATHROOM, 5), (R.TOILET, 2), (R.HALLWAY, 6)],
    "family": [(R.LIVING_ROOM, 24), (R.BEDROOM, 15), (R.BEDROOM, 11), (R.BEDROOM, 11), (R.KITCHEN, 12), (R.BATHROOM, 5), (R.TOILET, 2), (R.UTILITY, 4), (R.HALLWAY, 7)],
    "rental": [(R.LIVING_ROOM, 16), (R.BEDROOM, 12), (R.BEDROOM, 12), (R.KITCHEN, 9), (R.BATHROOM, 4), (R.TOILET, 2), (R.HALLWAY, 5)],
}


def _gen(spec, openness):
    rooms = [RoomInput(room_type=t, area_m2=a) for t, a in spec]
    rooms.append(RoomInput(room_type=R.GARAGE, area_m2=22))
    params = BuildingParams(rooms=rooms, country=CountryCode.KZ, floors=1,
                            building_shape="rectangular", openness=openness)
    return LayoutEngine(params, geo).generate()


def _garage_door_targets(rooms):
    g = next(r for r in rooms if r.room_type == R.GARAGE)
    fr = [r for r in rooms if r.floor == g.floor]
    return [t for d in g.doors if d.kind != "gate" and (t := _door_target(g, d, fr))]


def _rule10(rooms, openness):
    return [v for v in check_invariants(rooms, openness=openness) if v.rule == 10]


@pytest.mark.parametrize("name", ["single", "couple", "rental"])
@pytest.mark.parametrize("openness", ["mixed", "open"])
def test_no_utility_presets_get_a_buffer_in_open_modes(name, openness):
    rooms = _gen(PRESETS[name], openness)
    targets = _garage_door_targets(rooms)
    assert targets, "garage must reach the house"
    for t in targets:
        assert t.room_type in TRUE_BUFFER, (
            f"{name}/{openness}: garage opens into {t.room_type.value}, expected hallway/utility"
        )
    errors = [v for v in _rule10(rooms, openness) if v.severity == "ERROR"]
    assert not errors, [v.message for v in errors]


@pytest.mark.parametrize("openness", ["closed", "mixed", "open"])
def test_family_with_utility_stays_clean(openness):
    rooms = _gen(PRESETS["family"], openness)
    for t in _garage_door_targets(rooms):
        assert t.room_type in TRUE_BUFFER
    assert not _rule10(rooms, openness)


@pytest.mark.parametrize("name", ["single", "couple", "rental"])
def test_closed_is_buffer_or_honest_warning_never_silent_or_error(name):
    rooms = _gen(PRESETS[name], "closed")
    targets = _garage_door_targets(rooms)
    assert targets
    r10 = _rule10(rooms, "closed")
    assert all(v.severity != "ERROR" for v in r10), "closed must not be a hard ERROR"
    for t in targets:
        assert t.room_type not in FORBIDDEN
        if t.room_type in SOFT_BUFFER:
            # kitchen/living fallback is allowed but must be flagged, not silent
            assert any(v.severity == "WARNING" for v in r10), (
                f"{name}/closed: garage→{t.room_type.value} must be an honest WARNING"
            )
        else:
            assert t.room_type in TRUE_BUFFER


def test_soft_buffer_is_warning_severity_not_error():
    # A garage that can only reach a kitchen (soft buffer) is a WARNING, so the
    # route surfaces amber, not a red ERROR count.
    from models import DoorSpec, RoomLayout

    def room(rid, rt, x, y, w, d, doors=None):
        return RoomLayout(room_id=rid, room_type=rt, name=rid, x=x, y=y, floor=1,
                          width=w, depth=d, area_m2=w * d, doors=doors or [])

    rooms = [
        room("hall", R.HALLWAY, 0, 0, 6, 1.4, doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),
        room("kitchen", R.KITCHEN, 0, 1.4, 6, 3, doors=[DoorSpec(wall="S", position=1.0, width=0.8)]),
        room("bath", R.BATHROOM, 6, 0, 3, 4.4, doors=[DoorSpec(wall="W", position=1.5, width=0.7)]),
        room("gar", R.GARAGE, 0, 4.4, 6, 3, doors=[DoorSpec(wall="S", position=2.0, width=0.9)]),
    ]
    r10 = [v for v in check_invariants(rooms, openness="closed") if v.rule == 10]
    assert r10, "garage→kitchen with no buffer must be flagged"
    assert all(v.severity == "WARNING" for v in r10)
