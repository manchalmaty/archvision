"""Every household preset at its defaults must generate CLEAN (no red flags).

These programs mirror frontend/src/presets.ts — the demo's storefront. A red
flag on the first click of a mainstream preset is a reputation bug even when
the flag itself is honest. (family with 3–4 kids on ONE floor is genuinely
over-programmed and MAY flag red — that case is deliberately not pinned here.)

The family bug this guards against: UTILITY banded with the bedrooms became a
0.65 m sliver in the deep dry band → tiled fallback → rule-4/9 reds. UTILITY
is plumbing and lives in the wet band (layout WET_ZONES now matches
mep.pipe_router.WET_ZONES).
"""

import pytest

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType

geo = GeoClimateCalculator().calculate(CountryCode.KZ, None, 1)

R = RoomType
PRESETS = {
    "single": [(R.LIVING_ROOM, 18), (R.BEDROOM, 12), (R.KITCHEN, 9), (R.BATHROOM, 4), (R.HALLWAY, 5)],
    "couple": [
        (R.LIVING_ROOM, 20),
        (R.BEDROOM, 14),
        (R.KITCHEN, 10),
        (R.BATHROOM, 5),
        (R.TOILET, 2),
        (R.HALLWAY, 6),
    ],
    "family_2kids": [
        (R.LIVING_ROOM, 24),
        (R.BEDROOM, 15),
        (R.BEDROOM, 11),
        (R.BEDROOM, 11),
        (R.KITCHEN, 12),
        (R.BATHROOM, 5),
        (R.TOILET, 2),
        (R.UTILITY, 4),
        (R.HALLWAY, 7),
    ],
    "rental": [
        (R.LIVING_ROOM, 18),
        (R.BEDROOM, 12),
        (R.BEDROOM, 12),
        (R.KITCHEN, 9),
        (R.BATHROOM, 4),
        (R.TOILET, 2),
        (R.HALLWAY, 6),
    ],
}


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("garage", [False, True], ids=["no_garage", "garage"])
def test_preset_defaults_generate_clean(preset, garage):
    rooms_in = [RoomInput(room_type=t, area_m2=a) for t, a in PRESETS[preset]]
    if garage:
        rooms_in.append(RoomInput(room_type=R.GARAGE, area_m2=22))
    params = BuildingParams(rooms=rooms_in, country=CountryCode.KZ, floors=1)
    rooms = LayoutEngine(params, geo).generate()
    violations = check_invariants(rooms)
    # No RED (ERROR) flag on a mainstream preset. In closed mode a garage doors
    # into the kitchen (a soft buffer) → an honest rule-10 WARNING (amber, "add a
    # mudroom for ideal"), which is allowed — it is not a red flag and never a
    # silent green.
    errors = [v for v in violations if v.severity == "ERROR"]
    assert errors == [], [f"{v.rule}: {v.message}" for v in errors]
    assert all(v.rule == 10 and v.severity == "WARNING" for v in violations), (
        [f"{v.rule}/{v.severity}: {v.message}" for v in violations]
    )
