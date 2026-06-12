import pytest

from core.cost_estimator import CURRENCY_INFO, CostEstimator
from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from mep.clash_detector import ClashDetector
from mep.pipe_router import PipeRouter
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
            assert c.conflict_type in ("pipe_pipe_clash", "pipe_wall_penetration")
            assert c.severity in ("HIGH", "MEDIUM", "LOW")
            assert c.conflict_id
            assert c.description

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
            assert cost.total_cost_local == pytest.approx(
                cost.total_cost_usd * rate, rel=0.01
            )

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

    def test_thicker_walls_cost_more(self, basic_params):
        layouts = LayoutEngine(basic_params, geo).generate()
        cold_geo = GeoClimateCalculator().calculate(CountryCode.RU, "Сибирь", 1)
        warm_geo = GeoClimateCalculator().calculate(CountryCode.UZ, None, 1)
        cold = CostEstimator(layouts, cold_geo, CountryCode.US).estimate()
        warm = CostEstimator(layouts, warm_geo, CountryCode.US).estimate()
        assert cold.total_cost_usd > warm.total_cost_usd
