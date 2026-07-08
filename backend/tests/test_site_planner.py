"""Site placement v1 — house on its plot, RK setbacks + coverage.

The layout engine draws the *building*; the site planner places that building on
the plot and judges it against the rules regional IZHS practice enforces:
a 5 m street (red-line) setback, a 3 m neighbour setback on the other sides,
and a 30% maximum plot coverage. Like the plan invariants it is deterministic
and honest — an over-large program on a tight plot ships a red SITE-* issue,
never a silent green.
"""

import pytest

from core.site_planner import (
    MAX_COVERAGE,
    NEIGHBOR_SETBACK_M,
    STREET_SETBACK_M,
    check_site,
    plan_site,
)
from models import RoomLayout, RoomType


def _room(rid, x, y, w, d, floor=1, rt=RoomType.LIVING_ROOM):
    return RoomLayout(
        room_id=rid, room_type=rt, name=rid, x=x, y=y, floor=floor,
        width=w, depth=d, area_m2=w * d,
    )


def _house(bw, bd, floor=1):
    """A single-rectangle footprint bw×bd anchored at the origin."""
    return [_room("r", 0.0, 0.0, bw, bd, floor=floor)]


class TestFootprintAndPlacement:
    def test_front_placed_at_street_setback_south(self):
        site = plan_site(_house(8, 8), plot_width=20, plot_depth=25, street_side="S")
        # front edge (south, min-y) sits exactly one street setback off the street
        assert site.clearances["S"] == pytest.approx(STREET_SETBACK_M, abs=0.01)
        # laterally centred → equal side gaps
        assert site.clearances["W"] == pytest.approx(site.clearances["E"], abs=0.01)

    def test_street_side_north_puts_front_at_top(self):
        site = plan_site(_house(8, 8), plot_width=20, plot_depth=25, street_side="N")
        assert site.clearances["N"] == pytest.approx(STREET_SETBACK_M, abs=0.01)

    def test_street_side_west_puts_front_at_left(self):
        site = plan_site(_house(8, 8), plot_width=25, plot_depth=20, street_side="W")
        assert site.clearances["W"] == pytest.approx(STREET_SETBACK_M, abs=0.01)

    def test_footprint_uses_ground_floor_bbox_only(self):
        rooms = _house(8, 8) + _house(30, 30, floor=2)  # huge upper floor is ignored
        site = plan_site(rooms, plot_width=20, plot_depth=25, street_side="S")
        assert site.building_width_m == pytest.approx(8, abs=0.01)
        assert site.building_depth_m == pytest.approx(8, abs=0.01)


class TestSetbackRule:
    def test_comfortable_house_has_no_violations(self):
        site = plan_site(_house(8, 8), plot_width=20, plot_depth=25, street_side="S")
        assert check_site(site) == []

    def test_too_wide_trips_a_side_setback(self):
        # plot 20 wide, neighbour setback 3 each side → max buildable width 14.
        site = plan_site(_house(16, 8), plot_width=20, plot_depth=25, street_side="S")
        vios = check_site(site)
        assert any(v.rule == 1 for v in vios), vios
        assert any("setback" in v.message.lower() for v in vios)

    def test_street_side_edge_needs_the_bigger_setback(self):
        # depth leaves 4 m in front — fine for a 3 m neighbour edge, short of the
        # 5 m street edge. Only violates because south is the street side.
        site = plan_site(_house(8, 21), plot_width=20, plot_depth=25, street_side="S")
        vios = check_site(site)
        assert any(v.rule == 1 and v.code == "S" for v in vios), vios


class TestCoverageRule:
    def test_over_coverage_flags_rule_2(self):
        # 12×12 = 144 m² on a 20×20 = 400 m² plot → 36% > 30%.
        site = plan_site(_house(12, 12), plot_width=20, plot_depth=20, street_side="S")
        assert site.coverage_ratio == pytest.approx(0.36, abs=0.01)
        vios = check_site(site)
        assert any(v.rule == 2 for v in vios)
        assert any(f"{int(MAX_COVERAGE * 100)}" in v.message for v in vios)

    def test_under_coverage_is_clean(self):
        site = plan_site(_house(8, 8), plot_width=25, plot_depth=25, street_side="S")
        assert site.coverage_ratio < MAX_COVERAGE
        assert all(v.rule != 2 for v in check_site(site))


class TestSeismicFlag:
    def test_flag_raised_in_high_seismic_zone(self):
        site = plan_site(_house(8, 8), plot_width=20, plot_depth=25,
                         street_side="S", seismic_zone=4)
        assert site.seismic_flag is True

    def test_no_flag_in_calm_zone(self):
        site = plan_site(_house(8, 8), plot_width=20, plot_depth=25,
                         street_side="S", seismic_zone=1)
        assert site.seismic_flag is False
