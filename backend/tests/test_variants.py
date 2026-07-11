"""Cost-Δ variant decision table (roadmap: variant comparison).

The same room program re-tiled at three FIXED spaciousness settings by the
deterministic rule engine — never the LLM — sorted by cost, each row carrying
the delta vs the cheapest row, the dominant driver of that delta, and an honest
ERROR count. The council bar: a decision table (cost is the sort key), causally
explained («Δ … because −8 m² → −14 m³ concrete»), reproducible — NOT a
swipeable plan gallery.
"""

from fastapi.testclient import TestClient

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from core.site_planner import check_site, plan_site
from core.variants import build_variants
from main import app
from models import BuildingParams, CountryCode, GenerationResult

client = TestClient(app)

PROGRAM = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 20},
        {"room_type": "kitchen", "area_m2": 12},
        {"room_type": "bedroom", "area_m2": 14},
        {"room_type": "bedroom", "area_m2": 12},
        {"room_type": "bathroom", "area_m2": 5},
        {"room_type": "toilet", "area_m2": 2},
        {"room_type": "hallway", "area_m2": 6},
    ],
    "country": "KZ",
    "floors": 1,
    "building_shape": "rectangular",
}


def _params(**over) -> BuildingParams:
    return BuildingParams(**{**PROGRAM, **over})


def _geo(params: BuildingParams):
    return GeoClimateCalculator().calculate(params.country, params.region, params.floors)


def test_three_rows_sorted_by_cost():
    p = _params()
    rows = build_variants(p, _geo(p), CountryCode.KZ)
    assert [r.label for r in sorted(rows, key=lambda r: r.spaciousness)] == [
        "compact",
        "balanced",
        "roomy",
    ]
    costs = [r.total_cost_local for r in rows]
    assert costs == sorted(costs)  # cost IS the sort key
    assert rows[0].delta_local == 0
    assert rows[0].delta_driver == ""


def test_deltas_are_causal_and_consistent():
    p = _params()
    rows = build_variants(p, _geo(p), CountryCode.KZ)
    base = rows[0]
    for row in rows[1:]:
        # The printed delta must BE the difference of the printed totals.
        assert row.delta_local == round(row.total_cost_local - base.total_cost_local, 0)
        assert row.delta_driver in ("concrete", "walls")
        assert row.delta_footprint_m2 > 0  # more money must buy more metres
        assert row.delta_concrete_m3 > 0


def test_deterministic_reproducible():
    p = _params()
    geo = _geo(p)
    assert build_variants(p, geo, CountryCode.KZ) == build_variants(p, geo, CountryCode.KZ)


def test_caller_params_not_mutated():
    p = _params(spaciousness=0.7)
    build_variants(p, _geo(p), CountryCode.KZ)
    assert p.spaciousness == 0.7


def test_red_flags_mirror_the_actual_checkers():
    # Honesty contract: the row's flag count must equal what the invariant and
    # site checkers actually see on a fresh deterministic re-tile — a cheaper
    # row that breaks minimum room sizes must say so in the row itself.
    p = _params(plot_width_m=12.0, plot_depth_m=20.0, openness="mixed")
    geo = _geo(p)
    rows = build_variants(p, geo, CountryCode.KZ)
    assert rows
    for row in rows:
        p2 = p.model_copy(update={"spaciousness": row.spaciousness}, deep=True)
        rooms = LayoutEngine(p2, geo).generate()
        expected = sum(
            1 for v in check_invariants(rooms, openness=p2.openness) if v.severity == "ERROR"
        )
        site = plan_site(rooms, p2.plot_width_m, p2.plot_depth_m, p2.street_side, geo.seismic_zone)
        expected += len(check_site(site))
        assert row.red_flags == expected


def test_variants_ride_on_the_api_result_and_persist():
    r = client.post("/api/v1/generate-plan", json=PROGRAM)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert {v["label"] for v in body["variants"]} == {"compact", "balanced", "roomy"}
    assert all(v["currency"] == "KZT" for v in body["variants"])
    # Share/history must reload the table: it lives inside the stored result.
    stored = client.get(f"/api/v1/projects/{body['project_id']}")
    assert stored.status_code == 200
    assert stored.json()["variants"] == body["variants"]


def test_old_stored_results_still_load():
    # Pre-variants {id}.json has no "variants" key — it must still validate.
    r = client.post("/api/v1/generate-plan", json=PROGRAM)
    data = r.json()
    data.pop("variants")
    assert GenerationResult.model_validate(data).variants == []
