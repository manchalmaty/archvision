"""Garage connects to the house only through a transitional buffer.

A garage is a dirty, cold, fumey space. Its person-door belongs into a mudroom /
hallway / utility (a transitional buffer), never directly into a bedroom,
bathroom, or toilet — you would track exhaust and dirt straight into a private
or wet room. Kitchen is a permitted fallback (fumes into the cooking zone is a
compromise, not the ideal), living last.

Two guards:
  * the engine's garage-door planner refuses to open into a forbidden room and
    prefers the buffer order hallway → utility → kitchen → living;
  * invariant rule 10 flags any plan (LLM, manual edit) where the garage opens
    directly into a bedroom/bath/toilet, or can only reach the house through one.
"""

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine, _door_target
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, DoorSpec, RoomInput, RoomLayout, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

FORBIDDEN = {RoomType.BEDROOM, RoomType.BATHROOM, RoomType.TOILET}


def _room(rid, rt, x, y, w, d, floor=1, doors=None):
    return RoomLayout(
        room_id=rid, room_type=rt, name=rid, x=x, y=y, floor=floor,
        width=w, depth=d, area_m2=w * d, doors=doors or [],
    )


class TestEnginePreference:
    def test_garage_person_door_never_opens_into_wet_or_private(self):
        params = BuildingParams(
            rooms=[
                RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
                RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
                RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
                RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
                RoomInput(room_type=RoomType.TOILET, area_m2=2),
                RoomInput(room_type=RoomType.UTILITY, area_m2=6),
                RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
                RoomInput(room_type=RoomType.GARAGE, area_m2=20),
            ],
            country=CountryCode.KZ, floors=1, building_shape="rectangular",
        )
        layouts = LayoutEngine(params, geo).generate()
        garage = next(r for r in layouts if r.room_type == RoomType.GARAGE)
        floor_rooms = [r for r in layouts if r.floor == garage.floor]
        interior_doors = [d for d in garage.doors if d.kind != "gate"]
        for d in interior_doors:
            target = _door_target(garage, d, floor_rooms)
            assert target is not None
            assert target.room_type not in FORBIDDEN, (
                f"garage opens into {target.room_type} — must route through a buffer"
            )

    def test_garage_program_has_no_rule10_violation(self):
        params = BuildingParams(
            rooms=[
                RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
                RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
                RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
                RoomInput(room_type=RoomType.TOILET, area_m2=2),
                RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
                RoomInput(room_type=RoomType.GARAGE, area_m2=20),
            ],
            country=CountryCode.KZ, floors=1, building_shape="rectangular",
        )
        layouts = LayoutEngine(params, geo).generate()
        assert all(v.rule != 10 for v in check_invariants(layouts))


class TestRule10:
    def _minimal_house(self, garage_doors):
        """A tiny but rule-valid house: kitchen+bath present, everything doored,
        so the ONLY thing under test is the garage's connection."""
        return [
            _room("hall", RoomType.HALLWAY, 4, 0, 3, 4,
                  doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),
            _room("kit", RoomType.KITCHEN, 0, 0, 4, 4,
                  doors=[DoorSpec(wall="E", position=1.5, width=0.8)]),
            _room("bath", RoomType.BATHROOM, 7, 0, 3, 4,
                  doors=[DoorSpec(wall="W", position=1.5, width=0.7)]),
            _room("gar", RoomType.GARAGE, 4, 4, 3, 5, doors=garage_doors),
        ]

    def test_direct_door_into_bathroom_flags_rule10(self):
        # Garage (north band) doored into the hallway's north wall is fine; here
        # we force its person-door onto the bathroom instead.
        bath = _room("bath", RoomType.BATHROOM, 4, 4, 3, 5)  # placed north of hall
        rooms = [
            _room("hall", RoomType.HALLWAY, 0, 0, 4, 4,
                  doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),
            _room("kit", RoomType.KITCHEN, 4, 0, 4, 4,
                  doors=[DoorSpec(wall="W", position=1.5, width=0.8)]),
            bath,
            _room("gar", RoomType.GARAGE, 4, 9, 3, 5,
                  doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),  # opens onto bath (y=9 south = bath north at y=9)
        ]
        # bath spans y[4..9]; garage at y[9..14], its S wall (y=9) meets bath N wall.
        vios = check_invariants(rooms)
        assert any(v.rule == 10 for v in vios), vios

    def test_door_into_hallway_is_clean(self):
        # Garage opens into the hallway (a buffer) — no rule-10 violation.
        rooms = [
            _room("hall", RoomType.HALLWAY, 0, 0, 4, 4,
                  doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),
            _room("kit", RoomType.KITCHEN, 4, 0, 4, 4,
                  doors=[DoorSpec(wall="W", position=1.5, width=0.8)]),
            _room("bath", RoomType.BATHROOM, 8, 0, 3, 4,
                  doors=[DoorSpec(wall="W", position=1.5, width=0.7)]),
            _room("gar", RoomType.GARAGE, 0, 4, 4, 5,
                  doors=[DoorSpec(wall="S", position=1.0, width=0.9)]),  # opens onto hallway
        ]
        assert all(v.rule != 10 for v in check_invariants(rooms))
