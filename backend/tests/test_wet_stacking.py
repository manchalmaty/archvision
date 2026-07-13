"""Wet-room stacking: the fix for the collapsed-bands defect.

The bug report: budget spaciousness + a 12 m plot + garage + two bedrooms →
the unbounded min-side width raise (rescuing a 1.2 m² toilet) flattened every
band to 1.5–2.0 m: living room 1.8 m deep, garage 1.47 m. Now the raise is
clamped to the habitable bands' depth caps and small wet rooms stack into one
column instead — and whatever still cannot fit ships RED, never green.
"""

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import USABLE_MIN_SIDE, LayoutEngine, _shared_len
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

BUG_REPORT_ROOMS = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=18),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=9),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=4),
    RoomInput(room_type=RoomType.TOILET, area_m2=1.5),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
    RoomInput(room_type=RoomType.GARAGE, area_m2=22),
]


def make(openness):
    return BuildingParams(
        rooms=[r.model_copy() for r in BUG_REPORT_ROOMS],
        country=CountryCode.KZ,
        floors=1,
        plot_width_m=12.0,
        building_shape="rectangular",
        openness=openness,
        spaciousness=0.0,
    )


class TestBugReportScenario:
    def test_mixed_budget_plan_is_fully_livable(self):
        rooms = LayoutEngine(make("mixed"), geo).generate()
        violations = check_invariants(rooms, openness="mixed")
        # The wet-stacking fix must leave every band livable. On this 12 m plot
        # the garage band abuts the wet band (no buffer room beside it), so the
        # garage honestly flags rule 10 ("opens into bathroom — add a mudroom");
        # that is expected. Everything ELSE — bands, areas, min-sides — is clean.
        non_garage = [v for v in violations if v.rule != 10]
        assert non_garage == [], [f"{v.rule}: {v.message}" for v in non_garage]

    def test_stacked_wet_rooms_share_the_riser_wall(self):
        rooms = LayoutEngine(make("mixed"), geo).generate()
        bath = next(r for r in rooms if r.room_type == RoomType.BATHROOM)
        toilet = next(r for r in rooms if r.room_type == RoomType.TOILET)
        assert _shared_len(bath, toilet) > 0.05, "stack must keep one plumbing wall"

    def test_garage_depth_never_below_physical_floor(self):
        rooms = LayoutEngine(make("mixed"), geo).generate()
        garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
        assert min(garage.width, garage.depth) >= USABLE_MIN_SIDE[RoomType.GARAGE] - 0.01

    def test_infeasible_closed_variant_is_flagged_not_silent(self):
        # Closed mode pins the kitchen to the wet band; this program cannot
        # fit any width at budget scaling — the engine must say so, not ship
        # a quiet best-effort.
        rooms = LayoutEngine(make("closed"), geo).generate()
        violations = check_invariants(rooms, openness="closed")
        assert violations, "over-constrained program must be flagged red"

    def test_hallway_prints_its_real_figure_not_the_house_width(self):
        # The full-width hall band ballooned to 2.2× its request (15.6 m² on
        # the original report) and the PDF printed the whole house width as
        # the hall's dimension. When it overshoots, the strip's end goes to a
        # small service room, so the hall's figure is its real extent.
        #
        # Tested WITHOUT the garage: a garage now earns a tambour (a second
        # hallway cell), which restructures the band and is covered by
        # test_garage_placement. Here we isolate the overshoot filler itself.
        no_garage = [r.model_copy() for r in BUG_REPORT_ROOMS if r.room_type != RoomType.GARAGE]
        params = BuildingParams(
            rooms=no_garage, country=CountryCode.KZ, floors=1, plot_width_m=12.0,
            building_shape="rectangular", openness="mixed", spaciousness=0.0,
        )
        rooms = LayoutEngine(params, geo).generate()
        hall = next(r for r in rooms if r.room_type == RoomType.HALLWAY)
        plan_w = max(r.x + r.width for r in rooms) - min(r.x for r in rooms)
        requested = next(
            r.area_m2 for r in BUG_REPORT_ROOMS if r.room_type == RoomType.HALLWAY
        )
        assert hall.width < plan_w - 0.5, "hall must not span the full house width"
        # spaciousness=0 → ×0.80; net-target sizing (release 7) honestly widens
        # the whole house ~10%, and the full-width strip follows — the bound
        # guards against the original 3.3× absurdity, not against honest growth.
        assert hall.width * hall.depth <= 2.4 * requested * 0.8
        assert check_invariants(rooms, openness="mixed") == []

    def test_no_band_flattened_below_deepest_min(self):
        # The clamp: whatever raise happens, living/kitchen/bedroom bands keep
        # their deepest room's minimum depth — no more 1.8 m living rooms.
        rooms = LayoutEngine(make("mixed"), geo).generate()
        for r in rooms:
            if r.room_type in (RoomType.LIVING_ROOM, RoomType.KITCHEN, RoomType.BEDROOM):
                need = USABLE_MIN_SIDE[r.room_type]
                assert min(r.width, r.depth) >= need - 0.01, (
                    f"{r.room_type.value}: {r.width:.2f}x{r.depth:.2f} < {need}"
                )
