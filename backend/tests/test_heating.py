"""Heating layer (release 3): envelope heat loss + boiler sizing + cost line.

Sketch-level but physically honest, like the cost model: the U-value method
over the real geo-driven wall/insulation thicknesses, the same 30% window
fraction the cost model assumes, ventilation air change. The design winter
temperature is DERIVED from the same climate index (AFI) that drives frost
depth — a draft figure with an honest label, not a СП 131 lookup.
"""

import math

from fastapi.testclient import TestClient

from core.geo_calculator import GeoClimateCalculator
from core.heat_calculator import estimate_heating
from core.layout_engine import LayoutEngine
from main import app
from models import BuildingParams, CountryCode, GenerationResult, RoomInput, RoomType

client = TestClient(app)
calc = GeoClimateCalculator()

PROGRAM = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
    RoomInput(room_type=RoomType.TOILET, area_m2=2),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
]


def _rooms(country=CountryCode.RU, region=None, garage=False):
    rooms = list(PROGRAM)
    if garage:
        rooms = rooms + [RoomInput(room_type=RoomType.GARAGE, area_m2=22)]
    params = BuildingParams(rooms=rooms, country=country, region=region, floors=1)
    geo = calc.calculate(country, region, 1)
    return LayoutEngine(params, geo).generate(), geo


def test_design_temp_derived_from_climate_index():
    moscow = calc.calculate(CountryCode.RU, "Москва", 1)
    siberia = calc.calculate(CountryCode.RU, "Сибирь", 1)
    almaty = calc.calculate(CountryCode.KZ, "Алматы", 1)
    astana = calc.calculate(CountryCode.KZ, "Астана", 1)
    assert -32 <= moscow.design_temp_c <= -20  # СП 131 Москва ≈ −28
    assert siberia.design_temp_c < moscow.design_temp_c
    assert astana.design_temp_c < almaty.design_temp_c


def test_heat_loss_in_sane_range():
    rooms, geo = _rooms(CountryCode.RU, "Москва")
    h = estimate_heating(rooms, geo)
    # A modern insulated single-family house sits around 40–120 W/m² of design
    # heat loss in this climate; outside that the physics is wrong somewhere.
    assert 40 <= h.specific_w_m2 <= 120, h
    assert h.boiler_kw >= h.heat_loss_kw * 1.2 - 0.01
    assert h.boiler_kw == math.ceil(h.boiler_kw)


def test_colder_region_needs_more_heat():
    rooms_s, geo_s = _rooms(CountryCode.RU, "Сибирь")
    rooms_k, geo_k = _rooms(CountryCode.RU, "Краснодар")
    hs = estimate_heating(rooms_s, geo_s)
    hk = estimate_heating(rooms_k, geo_k)
    assert hs.heat_loss_kw > hk.heat_loss_kw


def test_garage_is_not_heated():
    with_garage, geo = _rooms(garage=True)
    h = estimate_heating(with_garage, geo)
    heated = sum(r.width * r.depth for r in with_garage if r.room_type != RoomType.GARAGE)
    assert abs(h.heated_area_m2 - round(heated, 1)) < 0.11


def test_heating_rides_on_the_api_result_and_the_estimate():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [{"room_type": rt.room_type.value, "area_m2": rt.area_m2} for rt in PROGRAM],
            "country": "RU",
            "region": "Москва",
            "floors": 1,
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["heating"] is not None
    assert body["heating"]["boiler_kw"] > 0
    bd = body["cost_estimate"]["breakdown"]
    assert bd["heating_usd"] > 0
    # The hero total must BE the sum of its printed lines (no hidden costs).
    assert abs(sum(bd.values()) + 0 - body["cost_estimate"]["total_cost_usd"]) <= max(
        1.0, 0.001 * body["cost_estimate"]["total_cost_usd"]
    ) + len(bd)  # per-line rounding slack


def test_variants_price_heating_too():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [{"room_type": rt.room_type.value, "area_m2": rt.area_m2} for rt in PROGRAM],
            "country": "RU",
            "region": "Москва",
            "floors": 1,
        },
    )
    body = r.json()
    # Roomier variant → bigger envelope → the heating line must grow with it,
    # because variants use the SAME estimator as the hero figure.
    rows = sorted(body["variants"], key=lambda v: v["spaciousness"])
    assert rows[0]["total_cost_local"] < rows[-1]["total_cost_local"]


def test_old_stored_results_still_load():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [{"room_type": "bedroom", "area_m2": 15}],
            "country": "KZ",
            "floors": 1,
        },
    )
    data = r.json()
    data.pop("heating")
    data["geo_climate"].pop("design_temp_c")
    loaded = GenerationResult.model_validate(data)
    assert loaded.heating is None
    assert loaded.geo_climate.design_temp_c is None
