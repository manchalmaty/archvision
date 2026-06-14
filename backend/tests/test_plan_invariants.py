import pytest

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, DoorSpec, RoomInput, RoomLayout, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.RU, None, 1)


def room(rid, rtype, x, y, w, d, floor=1, doors=None, area=None):
    return RoomLayout(
        room_id=rid, room_type=rtype, name=rid, x=x, y=y, floor=floor,
        width=w, depth=d, area_m2=area if area is not None else w * d,
        doors=doors or [], windows=[],
    )


def door(wall):
    return DoorSpec(wall=wall, position=0.5, width=0.8, height=2.0)


def rules(violations):
    return {v.rule for v in violations}


class TestEnginePassesAllInvariants:
    @pytest.mark.parametrize("shape", ["rectangular", "square", "l_shape", "u_shape", "t_shape"])
    @pytest.mark.parametrize("floors", [1, 2])
    def test_generated_plan_has_no_violations(self, shape, floors):
        params = BuildingParams(
            rooms=[
                RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
                RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
                RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
                RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
                RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
                RoomInput(room_type=RoomType.TOILET, area_m2=3),
            ],
            country=CountryCode.RU, floors=floors, building_shape=shape,
        )
        layouts = LayoutEngine(params, geo).generate()
        violations = check_invariants(layouts)
        assert violations == [], [f"rule {v.rule} {v.code}: {v.message}" for v in violations]


class TestEachRuleCatchesAViolation:
    def test_rule1_overlap(self):
        plan = [room("a", RoomType.LIVING_ROOM, 0, 0, 4, 4, doors=[door("S")]),
                room("b", RoomType.BEDROOM, 2, 2, 4, 4, doors=[door("S")])]
        assert 1 in rules(check_invariants(plan))

    def test_rule1_gap(self):
        plan = [room("a", RoomType.LIVING_ROOM, 0, 0, 3, 3, doors=[door("S")]),
                room("b", RoomType.BEDROOM, 6, 0, 3, 3, doors=[door("S")])]
        assert 1 in rules(check_invariants(plan))

    def test_rule2_area_too_small(self):
        plan = [room("a", RoomType.LIVING_ROOM, 0, 0, 3, 3, doors=[door("S")], area=20)]
        assert 2 in rules(check_invariants(plan))

    def test_rule3_missing_door(self):
        plan = [room("a", RoomType.BEDROOM, 0, 0, 3, 3, doors=[])]
        assert 3 in rules(check_invariants(plan))

    def test_rule4_transit_through_bedroom(self):
        # hallway -> bedroom -> living; living is only reachable via the bedroom
        plan = [
            room("h", RoomType.HALLWAY, 0, 0, 3, 3, doors=[door("S")]),
            room("bed", RoomType.BEDROOM, 3, 0, 3, 3, doors=[door("W")]),
            room("liv", RoomType.LIVING_ROOM, 6, 0, 3, 3, doors=[door("W")]),
        ]
        assert 4 in rules(check_invariants(plan))

    def test_rule5_wet_zones_split(self):
        plan = [
            room("bath", RoomType.BATHROOM, 0, 0, 3, 3, doors=[door("E")]),
            room("h", RoomType.HALLWAY, 3, 0, 3, 3, doors=[door("S")]),
            room("toilet", RoomType.TOILET, 6, 0, 3, 3, doors=[door("W")]),
        ]
        assert 5 in rules(check_invariants(plan))

    def test_rule6_entrance_not_through_buffer(self):
        plan = [room("bed", RoomType.BEDROOM, 0, 0, 3, 3, doors=[door("S")])]  # door to outside
        assert 6 in rules(check_invariants(plan))

    def test_rule7_wet_not_over_wet(self):
        plan = [
            room("bath1", RoomType.BATHROOM, 0, 0, 3, 3, floor=1, doors=[door("S")]),
            room("bath2", RoomType.BATHROOM, 6, 0, 3, 3, floor=2, doors=[door("S")]),
        ]
        assert 7 in rules(check_invariants(plan))

    def test_rule8_missing_kitchen(self):
        plan = [
            room("h", RoomType.HALLWAY, 0, 0, 3, 3, doors=[door("S")]),
            room("bath", RoomType.BATHROOM, 3, 0, 3, 3, doors=[door("W")]),
        ]
        codes = {v.code for v in check_invariants(plan)}
        assert "no_kitchen" in codes

    def test_rule9_narrow_room_with_correct_area(self):
        # 12m² but 7.0×1.7m — area is fine, the room is unusable.
        plan = [room("liv", RoomType.LIVING_ROOM, 0, 0, 7.0, 1.7, doors=[door("S")], area=11.9)]
        assert 9 in rules(check_invariants(plan))
