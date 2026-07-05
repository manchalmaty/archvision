from core.cost_estimator import CostEstimator
from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

ROOMS = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=22),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=12),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
]


def make(s=None):
    kw = {} if s is None else {"spaciousness": s}
    return BuildingParams(
        rooms=[r.model_copy() for r in ROOMS],
        country=CountryCode.KZ,
        floors=1,
        building_shape="rectangular",
        **kw,
    )


def _area_cost(s):
    layouts = LayoutEngine(make(s), geo).generate()
    area = sum(r.width * r.depth for r in layouts)
    cost = CostEstimator(layouts, geo, CountryCode.KZ).estimate().total_cost_usd
    return area, cost


def test_default_is_neutral_midpoint():
    assert make().spaciousness == 0.5


def test_spacious_is_bigger_and_pricier_than_budget():
    a_lo, c_lo = _area_cost(0.1)
    a_mid, c_mid = _area_cost(0.5)
    a_hi, c_hi = _area_cost(0.9)
    assert a_lo < a_mid < a_hi, (a_lo, a_mid, a_hi)
    assert c_lo < c_mid < c_hi, (c_lo, c_mid, c_hi)


def test_budget_leaning_plan_still_valid():
    # A budget-leaning setting stays fully valid. (At the absolute floor the wet
    # band can get shallower than the kitchen min-side; that is the engine's
    # documented "honest shortfall", not a regression — the slider still works.)
    assert check_invariants(LayoutEngine(make(0.3), geo).generate()) == []


def test_budget_footprint_has_less_perimeter():
    # The budget end yields a smaller footprint, so less exterior wall and less
    # heat-loss surface than the spacious end.
    def perimeter(s):
        L = LayoutEngine(make(s), geo).generate()
        w = max(r.x + r.width for r in L) - min(r.x for r in L)
        d = max(r.y + r.depth for r in L) - min(r.y for r in L)
        return 2 * (w + d)

    assert perimeter(0.1) < perimeter(0.9)
