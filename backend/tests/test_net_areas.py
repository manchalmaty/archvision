"""Net (usable) areas (release 5): the walls stop silently eating metres.

Axis-line geometry stays the single structural model (the bbox IS the real
outer footprint — site placement and cost keep their basis), but every room
now carries honest net dimensions: the exterior wall grows INWARD from the
axis at its full geo-driven thickness, interior partitions take half their
120 mm on each side. The displayed axis figure stays primary; the net figure
is the second, explicitly labeled truth.
"""

from fastapi.testclient import TestClient

from core.cost_estimator import INTERIOR_WALL_T
from core.geo_calculator import GeoClimateCalculator
from core.walls import annotate_net_dims
from main import app
from models import CountryCode, GenerationResult, RoomLayout, RoomType

client = TestClient(app)
geo = GeoClimateCalculator().calculate(CountryCode.RU, "Москва", 1)
EXT_T = geo.wall_thickness_mm / 1000.0


def _room(rid, x, y, w, d, floor=1, rt=RoomType.BEDROOM):
    return RoomLayout(
        room_id=rid, room_type=rt, name="Bedroom", x=x, y=y, floor=floor,
        width=w, depth=d, area_m2=w * d,
    )


def test_two_room_floor_arithmetic():
    a = _room("a", 0, 0, 4, 5)
    b = _room("b", 4, 0, 4, 5)
    annotate_net_dims([a, b], geo)
    half = INTERIOR_WALL_T / 2
    # A: west/south/north edges are on the bbox (exterior), east is shared.
    assert abs(a.net_width - (4 - EXT_T - half)) < 1e-6
    assert abs(a.net_depth - (5 - 2 * EXT_T)) < 1e-6
    assert abs(a.net_area - a.net_width * a.net_depth) < 0.011  # 2dp rounding
    assert abs(b.net_width - a.net_width) < 1e-6  # mirror case


def test_net_is_always_smaller_than_axis():
    a = _room("a", 0, 0, 3, 3)
    annotate_net_dims([a], geo)
    assert 0 < a.net_area < a.width * a.depth


def test_floors_are_independent():
    ground = _room("g", 0, 0, 6, 6, floor=1)
    upper = _room("u", 0, 0, 4, 4, floor=2)
    annotate_net_dims([ground, upper], geo)
    # The upper room spans its OWN floor's bbox — all four edges exterior.
    assert abs(upper.net_width - (4 - 2 * EXT_T)) < 1e-6


def test_api_result_carries_net_dims():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [
                {"room_type": "living_room", "area_m2": 20},
                {"room_type": "kitchen", "area_m2": 10},
                {"room_type": "bedroom", "area_m2": 14},
                {"room_type": "bathroom", "area_m2": 5},
                {"room_type": "toilet", "area_m2": 2},
                {"room_type": "hallway", "area_m2": 6},
            ],
            "country": "RU",
            "region": "Москва",
            "floors": 1,
        },
    )
    assert r.status_code == 200, r.text[:300]
    for room in r.json()["rooms"]:
        assert room["net_area"] is not None
        assert room["net_area"] < room["width"] * room["depth"]


def test_old_stored_results_still_load():
    room = _room("a", 0, 0, 4, 4).model_dump()
    for k in ("net_width", "net_depth", "net_area"):
        room.pop(k)
    assert RoomLayout.model_validate(room).net_area is None


def test_pdf_prints_net_column():
    rooms = [_room("a", 0, 0, 4, 5), _room("b", 4, 0, 4, 5)]
    annotate_net_dims(rooms, geo)
    result = GenerationResult(
        project_id="test", rooms=rooms, geo_climate=geo, mep_conflicts=[],
        compliance_issues=[], cost_estimate={
            "concrete_m3": 1, "brick_m3": 1, "insulation_m2": 1,
            "total_cost_usd": 1, "total_cost_local": 1, "currency": "USD",
            "breakdown": {},
        }, ifc_file_url="", warnings=[],
    )
    from core.pdf_generator import generate_pdf

    pdf = generate_pdf(result, "ru")
    assert len(pdf) > 1000  # renders with the extra column, no crash
