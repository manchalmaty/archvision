import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

PARAMS = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 20},
        {"room_type": "bedroom", "area_m2": 14},
        {"room_type": "kitchen", "area_m2": 10},
        {"room_type": "bathroom", "area_m2": 5},
        {"room_type": "toilet", "area_m2": 2},
        {"room_type": "hallway", "area_m2": 6},
    ],
    "country": "KZ",
    "region": "Алматы",
    "floors": 2,
    "plot_width_m": 9.0,
    "plot_depth_m": 12.0,
    "building_shape": "rectangular",
}


DEVICE_TOKEN = "11111111-1111-1111-1111-111111111111"
OTHER_TOKEN = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(scope="module")
def generated():
    r = client.post("/api/v1/generate-plan", json=PARAMS, headers={"X-Device-Token": DEVICE_TOKEN})
    assert r.status_code == 200, r.text[:300]
    return r.json()


class TestGenerate:
    def test_response_shape(self, generated):
        for key in (
            "project_id",
            "rooms",
            "geo_climate",
            "mep_conflicts",
            "compliance_issues",
            "cost_estimate",
            "ifc_file_url",
            "warnings",
        ):
            assert key in generated

    def test_seismic_warning_for_almaty_2_floors(self, generated):
        # Алматы = seismic zone 4 → max 2 floors; request of 2 is fine, no warning
        assert generated["geo_climate"]["seismic_zone"] == 4

    def test_validation_rejects_empty_rooms(self):
        r = client.post("/api/v1/generate-plan", json={**PARAMS, "rooms": []})
        assert r.status_code == 422

    def test_validation_rejects_bad_floors(self):
        r = client.post("/api/v1/generate-plan", json={**PARAMS, "floors": 99})
        assert r.status_code == 422


class TestProjects:
    def test_get_project_roundtrip(self, generated):
        r = client.get(f"/api/v1/projects/{generated['project_id']}")
        assert r.status_code == 200
        assert r.json()["project_id"] == generated["project_id"]

    def test_list_projects_contains_generated(self, generated):
        r = client.get("/api/v1/projects", headers={"X-Device-Token": DEVICE_TOKEN})
        assert r.status_code == 200
        entries = r.json()
        assert any(e["project_id"] == generated["project_id"] for e in entries)
        entry = next(e for e in entries if e["project_id"] == generated["project_id"])
        assert entry["rooms"] == len(generated["rooms"])
        assert entry["floors"] == 2

    def test_list_without_token_is_empty(self, generated):
        r = client.get("/api/v1/projects")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_with_foreign_token_hides_project(self, generated):
        r = client.get("/api/v1/projects", headers={"X-Device-Token": OTHER_TOKEN})
        assert r.status_code == 200
        assert all(e["project_id"] != generated["project_id"] for e in r.json())

    def test_share_by_id_needs_no_token(self, generated):
        # Share-by-link stays public on purpose: the uuid4 IS the capability.
        r = client.get(f"/api/v1/projects/{generated['project_id']}")
        assert r.status_code == 200
        assert "_owner" not in r.json()

    def test_raw_store_not_exposed(self, generated):
        # The stored JSON carries the private _owner device token — it must
        # never be reachable as a static file (only via model-validated routes).
        r = client.get(f"/files/{generated['project_id']}.json")
        assert r.status_code == 404

    def test_missing_project_404(self):
        r = client.get("/api/v1/projects/00000000-dead-beef-0000-000000000000")
        assert r.status_code == 404

    @pytest.mark.parametrize("bad_id", ["..", "%2e%2e", "not-a-uuid", "a" * 36])
    def test_non_uuid_rejected(self, bad_id):
        for endpoint in ("projects", "report", "download"):
            r = client.get(f"/api/v1/{endpoint}/{bad_id}")
            assert r.status_code in (404, 422), f"{endpoint}/{bad_id}: {r.status_code}"


class TestReport:
    @pytest.mark.parametrize("lang", ["en", "ru", "kk"])
    def test_pdf_in_all_languages(self, generated, lang):
        r = client.get(f"/api/v1/report/{generated['project_id']}", params={"lang": lang})
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        assert r.headers["content-type"] == "application/pdf"

    def test_invalid_lang_422(self, generated):
        r = client.get(f"/api/v1/report/{generated['project_id']}", params={"lang": "xx"})
        assert r.status_code == 422

    def test_report_embeds_floor_plan_drawing(self):
        # The report must contain the actual 2D scheme, not just tables: one
        # vector drawing per floor, with a rect per room and door/window lines.
        from reportlab.graphics.shapes import PolyLine, Rect

        from core.cost_estimator import CostEstimator
        from core.geo_calculator import GeoClimateCalculator
        from core.layout_engine import LayoutEngine
        from core.pdf_generator import _floor_plan_drawing
        from models import BuildingParams, CountryCode, RoomInput, RoomType

        geo = GeoClimateCalculator().calculate(CountryCode.RU, None, 1)
        params = BuildingParams(
            rooms=[
                RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=18),
                RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
                RoomInput(room_type=RoomType.KITCHEN, area_m2=9),
                RoomInput(room_type=RoomType.BATHROOM, area_m2=4),
            ],
            country=CountryCode.RU,
            floors=1,
        )
        rooms = LayoutEngine(params, geo).generate()
        CostEstimator(rooms, geo, CountryCode.RU).estimate()
        drawing = _floor_plan_drawing(rooms, 493.0, "Floor 1")
        rects = [e for e in drawing.contents if isinstance(e, Rect)]
        arcs = [e for e in drawing.contents if isinstance(e, PolyLine)]
        assert len(rects) == len(rooms)  # one poché room box each
        assert arcs  # door swing arcs present
        assert drawing.width > 0 and drawing.height > 0


class TestMisc:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_countries_list(self):
        r = client.get("/api/v1/countries")
        assert r.status_code == 200
        assert {c["code"] for c in r.json()} >= {"RU", "KZ", "US"}
