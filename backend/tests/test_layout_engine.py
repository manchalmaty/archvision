import itertools

import pytest

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from models import BuildingParams, CountryCode, RoomInput, RoomType
from tests.conftest import rooms_overlap

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

SHAPES = ["rectangular", "square", "l_shape", "u_shape", "t_shape"]


def make_params(**overrides) -> BuildingParams:
    base = {
        "rooms": [
            RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
            RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
            RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
            RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
            RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
            RoomInput(room_type=RoomType.TOILET, area_m2=2),
            RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
            RoomInput(room_type=RoomType.GARAGE, area_m2=18),
        ],
        "country": CountryCode.KZ,
        "floors": 1,
        "building_shape": "rectangular",
    }
    base.update(overrides)
    return BuildingParams(**base)


class TestEssentials:
    def test_hallway_and_toilet_injected(self):
        params = make_params(rooms=[RoomInput(room_type=RoomType.BEDROOM, area_m2=15)])
        layouts = LayoutEngine(params, geo).generate()
        types = {r.room_type for r in layouts}
        assert RoomType.HALLWAY in types
        assert RoomType.TOILET in types


class TestNoOverlaps:
    @pytest.mark.parametrize("shape", SHAPES)
    @pytest.mark.parametrize("floors", [1, 2, 3])
    def test_rooms_never_overlap(self, shape, floors):
        params = make_params(building_shape=shape, floors=floors)
        layouts = LayoutEngine(params, geo).generate()
        for a, b in itertools.combinations(layouts, 2):
            assert not rooms_overlap(a, b), f"{a.name} overlaps {b.name} ({shape}, fl{a.floor})"

    def test_all_requested_rooms_present(self):
        params = make_params()
        layouts = LayoutEngine(params, geo).generate()
        assert len(layouts) == len(params.rooms)  # essentials already included


class TestFloorDistribution:
    def test_wet_zones_on_ground_floor(self):
        params = make_params(floors=2)
        layouts = LayoutEngine(params, geo).generate()
        for room in layouts:
            if room.room_type in (RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET):
                assert room.floor == 1, f"{room.name} must be on the ground floor"

    def test_every_floor_gets_rooms(self):
        params = make_params(floors=2)
        layouts = LayoutEngine(params, geo).generate()
        assert {r.floor for r in layouts} == {1, 2}


class TestPlotConstraint:
    def test_rectangular_plot_width_strict(self):
        # Single-strip shapes can always honor the cap exactly.
        params = make_params(building_shape="rectangular", plot_width_m=9.0, plot_depth_m=30.0)
        layouts = LayoutEngine(params, geo).generate()
        assert max(r.x + r.width for r in layouts) <= 9.0 + 0.01

    @pytest.mark.parametrize("shape", SHAPES)
    def test_plot_fits_or_warns(self, shape):
        # Winged shapes (U/T) may be geometrically impossible on a narrow plot —
        # the contract is: fit within the plot, or emit an explicit warning.
        params = make_params(building_shape=shape, plot_width_m=9.0, plot_depth_m=30.0)
        engine = LayoutEngine(params, geo)
        layouts = engine.generate()
        building_width = max(r.x + r.width for r in layouts)
        fits = building_width <= 9.0 + 0.01
        warned = any("exceeds plot" in w for w in engine.warnings)
        assert fits or warned, f"{shape}: width {building_width}, no warning"

    @pytest.mark.parametrize("shape", SHAPES)
    def test_wide_plot_always_fits(self, shape):
        params = make_params(building_shape=shape, plot_width_m=40.0, plot_depth_m=40.0)
        engine = LayoutEngine(params, geo)
        layouts = engine.generate()
        assert max(r.x + r.width for r in layouts) <= 40.01
        assert engine.warnings == []

    def test_overflow_emits_warning(self):
        params = make_params(plot_width_m=4.0, plot_depth_m=4.0)
        engine = LayoutEngine(params, geo)
        engine.generate()
        assert any("exceeds plot" in w for w in engine.warnings)

    def test_no_warning_when_plot_fits(self):
        params = make_params(plot_width_m=50.0, plot_depth_m=50.0)
        engine = LayoutEngine(params, geo)
        engine.generate()
        assert engine.warnings == []


class TestOpenings:
    @pytest.mark.parametrize("shape", SHAPES)
    def test_every_room_has_a_door(self, shape):
        params = make_params(building_shape=shape)
        layouts = LayoutEngine(params, geo).generate()
        for room in layouts:
            assert room.doors, f"{room.name} has no door"

    @pytest.mark.parametrize("shape", SHAPES)
    def test_hallway_has_single_door(self, shape):
        # The hallway owns one entrance door; neighbours own the interior doors,
        # so the hallway must never accumulate a door per shared wall.
        params = make_params(building_shape=shape)
        layouts = LayoutEngine(params, geo).generate()
        for room in layouts:
            if room.room_type == RoomType.HALLWAY:
                assert len(room.doors) == 1, (
                    f"{shape}: hallway on floor {room.floor} has {len(room.doors)} doors"
                )

    def test_opening_positions_inside_walls(self):
        """Data-layer guarantee: position is clamped so openings never overflow."""
        params = make_params()
        layouts = LayoutEngine(params, geo).generate()
        eps = 0.01
        for room in layouts:
            for opening in [*room.doors, *room.windows]:
                wall_len = room.width if opening.wall in ("N", "S") else room.depth
                assert opening.position >= -eps
                max_pos = max(0.0, wall_len - opening.width)
                assert opening.position <= max_pos + eps, (
                    f"{room.name} {opening.wall}: pos {opening.position} "
                    f"+ w {opening.width} overflows wall {wall_len}"
                )

    def test_windows_only_on_external_walls(self):
        params = make_params()
        layouts = LayoutEngine(params, geo).generate()
        # A window's wall must not be shared with another room (it is external)
        from core.layout_engine import _adjacent_rooms

        for room in layouts:
            same_floor = [r for r in layouts if r.floor == room.floor]
            for win in room.windows:
                assert not _adjacent_rooms(
                    room, win.wall, same_floor
                ), f"{room.name}: window on internal wall {win.wall}"


class TestTiling:
    """Rectangular/square deterministic layouts must tile with no gaps and stay
    fully connected — the guarantee the LLM loop falls back on."""

    @pytest.mark.parametrize("shape", ["rectangular", "square"])
    def test_every_room_opens_off_the_hallway(self, shape):
        # Central-hall layouts must be a distribution node, not an enfilade:
        # every room on the ground floor borders the hallway directly.
        from core.layout_engine import _adjacent_rooms

        params = make_params(
            building_shape=shape,
            rooms=[
                RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
                RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
                RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
                RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
            ],
        )
        layouts = LayoutEngine(params, geo).generate()
        floor1 = [r for r in layouts if r.floor == 1]
        for room in floor1:
            if room.room_type == RoomType.HALLWAY:
                continue
            touches_hall = any(
                other.room_type == RoomType.HALLWAY
                for wall in ("N", "S", "E", "W")
                for other in _adjacent_rooms(room, wall, floor1)
            )
            assert touches_hall, f"{shape}: {room.name} does not border the hallway"

    @pytest.mark.parametrize("shape", ["rectangular", "square"])
    def test_clean_tiling_passes_validator(self, shape):
        from core.plan_validator import PlanRoom, validate_plan

        params = make_params(building_shape=shape)
        layouts = LayoutEngine(params, geo).generate()
        floor1 = [r for r in layouts if r.floor == 1]
        pr = [
            PlanRoom(r.room_id, r.room_type.value, r.name, r.x, r.y, r.width, r.depth)
            for r in floor1
        ]
        fw = max(r.x + r.width for r in floor1)
        fh = max(r.y + r.depth for r in floor1)
        errors, score = validate_plan(pr, fw, fh, shape)
        assert score == 100, f"{shape}: {errors}"


class TestAreaPreserved:
    def test_footprint_at_least_requested_area(self):
        # Rows are normalized to a common depth, so a room's footprint can be
        # LARGER than requested — but never meaningfully smaller.
        params = make_params()
        layouts = LayoutEngine(params, geo).generate()
        for room in layouts:
            assert (
                room.width * room.depth >= room.area_m2 * 0.95
            ), f"{room.name}: {room.width}x{room.depth} < requested {room.area_m2}"
