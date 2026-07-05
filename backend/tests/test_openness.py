import itertools

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine, _shared_len
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType
from tests.conftest import rooms_overlap

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

SOCIAL_OPENING_MIN = 1.6


def make(openness, **ov):
    return BuildingParams(
        rooms=[r.model_copy() for r in ROOMS],
        country=CountryCode.KZ,
        floors=1,
        building_shape="rectangular",
        openness=openness,
        **ov,
    )


def _floor1(params):
    return [r for r in LayoutEngine(params, geo).generate() if r.floor == 1]


def _kitchen_living_merged(floor) -> bool:
    """Kitchen and living are one social volume: adjacent + a wide opening."""
    k = next(r for r in floor if r.room_type == RoomType.KITCHEN)
    lv = next(r for r in floor if r.room_type == RoomType.LIVING_ROOM)
    if _shared_len(k, lv) < SOCIAL_OPENING_MIN:
        return False
    return any(d.kind == "opening" and d.width >= SOCIAL_OPENING_MIN for d in (*k.doors, *lv.doors))


class TestClosedUnchanged:
    def test_keeps_hallway(self):
        assert any(r.room_type == RoomType.HALLWAY for r in _floor1(make("closed")))

    def test_no_wide_social_opening(self):
        # Closed keeps every internal wall — no 1.6m+ cased opening.
        floor = _floor1(make("closed"))
        assert not any(d.kind == "opening" for r in floor for d in r.doors)

    def test_invariants_pass(self):
        assert check_invariants(LayoutEngine(make("closed"), geo).generate()) == []


class TestOpen:
    def test_keeps_entry_hallway(self):
        # Open plan keeps an entry buffer (тамбур) — it is just opened up, not removed.
        assert any(r.room_type == RoomType.HALLWAY for r in _floor1(make("open")))

    def test_kitchen_living_single_volume(self):
        assert _kitchen_living_merged(_floor1(make("open")))

    def test_entry_zone_opens_into_social(self):
        # The entry hallway flows into the social volume via a wide opening
        # (no walled corridor) — that is what makes it "open".
        floor = _floor1(make("open"))
        assert any(
            d.kind == "opening" for r in floor if r.room_type == RoomType.HALLWAY for d in r.doors
        )

    def test_invariants_pass(self):
        layouts = LayoutEngine(make("open"), geo).generate()
        assert check_invariants(layouts, openness="open") == []

    def test_no_overlaps(self):
        layouts = LayoutEngine(make("open"), geo).generate()
        for a, b in itertools.combinations(layouts, 2):
            assert not rooms_overlap(a, b)


class TestMixed:
    def test_keeps_hallway(self):
        assert any(r.room_type == RoomType.HALLWAY for r in _floor1(make("mixed")))

    def test_kitchen_living_single_volume(self):
        assert _kitchen_living_merged(_floor1(make("mixed")))

    def test_invariants_pass(self):
        layouts = LayoutEngine(make("mixed"), geo).generate()
        assert check_invariants(layouts, openness="mixed") == []
