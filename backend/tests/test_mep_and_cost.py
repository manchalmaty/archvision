import pytest

from core.cost_estimator import CURRENCY_INFO, CostEstimator
from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from mep.clash_detector import ClashDetector
from mep.pipe_router import FLOOR_HEIGHT, PipeRouter
from models import CountryCode

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)


@pytest.fixture
def layouts(basic_params):
    return LayoutEngine(basic_params, geo).generate()


class TestMEP:
    def test_router_produces_pipes_for_wet_zones(self, layouts, basic_params):
        pipes = PipeRouter(layouts, basic_params.floors, geo).route()
        assert pipes, "wet zones present — routing must produce pipe runs"

    def test_clash_detector_output_shape(self, layouts, basic_params):
        pipes = PipeRouter(layouts, basic_params.floors, geo).route()
        conflicts = ClashDetector(layouts, pipes).detect()
        for c in conflicts:
            assert c.conflict_type in ("pipe_pipe_clash", "pipe_through_room")
            assert c.severity in ("HIGH", "MEDIUM", "LOW")
            assert c.conflict_id
            assert c.description

    def test_no_conflicts_inside_dry_rooms_when_wet_grouped(self, layouts, basic_params):
        # With the central-hall layout grouping wet zones, no conflict should be
        # reported as being *inside* a bedroom/living room (the old bedroom noise).
        from mep.pipe_router import WET_ZONES

        pipes = PipeRouter(layouts, basic_params.floors, geo).route()
        conflicts = ClashDetector(layouts, pipes).detect()
        dry = [r for r in layouts if r.room_type not in WET_ZONES]
        for c in conflicts:
            for room in dry:
                inside = (
                    room.x < c.location_x < room.x + room.width
                    and room.y < c.location_y < room.y + room.depth
                )
                # If a marker IS inside a dry room it must be an explicit, actionable
                # "pipe routed through this room" — never silent noise.
                if inside:
                    assert c.conflict_type == "pipe_through_room"

    def test_pipe_through_bedroom_is_flagged(self):
        # Positive control: a bathroom stranded behind a bedroom forces a drain
        # across the bedroom — that must be reported (the feature isn't dead).
        from models import RoomLayout, RoomType

        rooms = [
            RoomLayout(
                room_id="k", room_type=RoomType.KITCHEN, name="Kitchen",
                x=0.0, y=0.0, floor=1, width=3.0, depth=3.0, area_m2=9.0,
            ),
            RoomLayout(
                room_id="bed", room_type=RoomType.BEDROOM, name="Bedroom",
                x=3.0, y=0.0, floor=1, width=4.0, depth=3.0, area_m2=12.0,
            ),
            RoomLayout(
                room_id="bath", room_type=RoomType.BATHROOM, name="Bathroom",
                x=7.0, y=0.0, floor=1, width=3.0, depth=3.0, area_m2=9.0,
            ),
        ]
        pipes = PipeRouter(rooms, 1, geo).route()
        conflicts = ClashDetector(rooms, pipes).detect()
        through = [c for c in conflicts if c.conflict_type == "pipe_through_room"]
        assert through, "a drain crossing the bedroom must be flagged"
        assert all("Bedroom" in c.description for c in through)

    def test_vertical_riser_connects_floors(self):
        # A pure pipe-router unit test: wet rooms on two floors must be tied by a
        # vertical riser stack spanning both storeys.
        from models import RoomLayout, RoomType

        rooms = [
            RoomLayout(
                room_id="b1", room_type=RoomType.BATHROOM, name="Bath 1",
                x=0, y=0, floor=1, width=2.5, depth=2.0, area_m2=5.0,
            ),
            RoomLayout(
                room_id="b2", room_type=RoomType.BATHROOM, name="Bath 2",
                x=0, y=0, floor=2, width=2.5, depth=2.0, area_m2=5.0,
            ),
        ]
        pipes = PipeRouter(rooms, 2, geo).route()
        risers = [p for p in pipes if p.pipe_type == "riser"]
        assert len(risers) == 1, "two wet floors must produce one vertical riser"
        zs = [pt[2] for pt in risers[0].points]
        assert max(zs) - min(zs) >= FLOOR_HEIGHT - 0.5, "riser must span both floors"

    def test_clash_detection_deterministic(self, layouts, basic_params):
        pipes = PipeRouter(layouts, basic_params.floors, geo).route()
        first = ClashDetector(layouts, pipes).detect()
        second = ClashDetector(layouts, pipes).detect()
        assert len(first) == len(second)


class TestCostEstimator:
    def test_positive_costs(self, layouts):
        cost = CostEstimator(layouts, geo, CountryCode.KZ).estimate()
        assert cost.total_cost_usd > 0
        assert cost.concrete_m3 > 0
        assert cost.brick_m3 > 0
        assert cost.insulation_m2 > 0

    def test_currency_mapping(self, layouts):
        for code, (currency, rate) in CURRENCY_INFO.items():
            cost = CostEstimator(layouts, geo, CountryCode(code)).estimate()
            assert cost.currency == currency
            assert cost.total_cost_local == pytest.approx(cost.total_cost_usd * rate, rel=0.01)

    def test_breakdown_sums_to_total(self, layouts):
        cost = CostEstimator(layouts, geo, CountryCode.US).estimate()
        assert sum(cost.breakdown.values()) == pytest.approx(cost.total_cost_usd, rel=0.01)

    def test_more_area_costs_more(self, basic_params):
        small = CostEstimator(
            LayoutEngine(basic_params, geo).generate(), geo, CountryCode.US
        ).estimate()

        big_params = basic_params.model_copy(deep=True)
        for room in big_params.rooms:
            room.area_m2 *= 2
        big = CostEstimator(
            LayoutEngine(big_params, geo).generate(), geo, CountryCode.US
        ).estimate()

        assert big.total_cost_usd > small.total_cost_usd

    def test_concrete_volume_is_realistic(self, layouts):
        # Regression: the old formula put solid-concrete partitions everywhere and
        # a full-area raft, giving ~1.6 m³ of concrete per m² of floor. A strip
        # foundation + slabs should sit well under ~1.2 m³/m².
        cost = CostEstimator(layouts, geo, CountryCode.RU).estimate()
        floor_area = sum(r.width * r.depth for r in layouts)
        assert cost.concrete_m3 / floor_area < 1.2

    def test_interior_walls_counted_once(self):
        # Two 3×3 rooms sharing a wall: exterior perimeter is the 6×3 box (18 m),
        # and the single shared partition is 3 m — not 6 m from summing perimeters.
        from core.cost_estimator import _floor_walls
        from models import RoomLayout, RoomType

        rooms = [
            RoomLayout(room_id="a", room_type=RoomType.BEDROOM, name="A",
                       x=0, y=0, floor=1, width=3, depth=3, area_m2=9),
            RoomLayout(room_id="b", room_type=RoomType.BEDROOM, name="B",
                       x=3, y=0, floor=1, width=3, depth=3, area_m2=9),
        ]
        exterior, interior = _floor_walls(rooms)
        assert exterior == pytest.approx(18.0)
        assert interior == pytest.approx(3.0)

    def test_thicker_walls_cost_more(self, basic_params):
        layouts = LayoutEngine(basic_params, geo).generate()
        cold_geo = GeoClimateCalculator().calculate(CountryCode.RU, "Сибирь", 1)
        warm_geo = GeoClimateCalculator().calculate(CountryCode.UZ, None, 1)
        cold = CostEstimator(layouts, cold_geo, CountryCode.US).estimate()
        warm = CostEstimator(layouts, warm_geo, CountryCode.US).estimate()
        assert cold.total_cost_usd > warm.total_cost_usd
