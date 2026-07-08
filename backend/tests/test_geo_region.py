"""Region resolution is global and honest (the Almaty-under-Russia safety bug).

Before: geo matched the region ONLY inside the selected country. Picking RU (to
get roubles) and typing "Алматы" fell through to the RU default — seismic zone 1
for a zone-4 city. A safety-critical wrong number shown as fact.

After: a global region index with match priority (exact-in-country → exact-global
→ substring). The matched region's country becomes the *effective country* that
drives currency, so you no longer pick a country just for its currency. An
unrecognized region flags a warning instead of silently using country averages.
"""

from fastapi.testclient import TestClient

from core.geo_calculator import GeoClimateCalculator
from main import app
from models import CountryCode

client = TestClient(app)
calc = GeoClimateCalculator()


class TestResolve:
    def test_almaty_under_russia_wins_globally(self):
        # THE anchor: RU selected, Алматы typed → Almaty's real seismicity, not RU.
        res = calc.resolve(CountryCode.RU, "Алматы")
        assert res.effective_country == "KZ"
        assert res.recognized is True

    def test_almaty_under_russia_seismic_is_four_not_one(self):
        geo = calc.calculate(CountryCode.RU, "Алматы", 1)
        assert geo.seismic_zone == 4, "Almaty is a high-seismic city — must not read RU zone 1"

    def test_exact_in_country_beats_global(self):
        # Краснодар exists in RU; even though other countries have regions, the
        # in-country exact match wins and effective country stays RU.
        res = calc.resolve(CountryCode.RU, "Краснодар")
        assert res.effective_country == "RU"
        assert res.matched_key == "Краснодар"

    def test_unrecognized_region_is_flagged_not_silent(self):
        res = calc.resolve(CountryCode.KZ, "Атлантида")
        assert res.recognized is False
        assert res.effective_country == "KZ"  # falls back to the selected country
        assert res.matched_key is None

    def test_empty_region_is_recognized_default(self):
        res = calc.resolve(CountryCode.KZ, None)
        assert res.recognized is True
        assert res.effective_country == "KZ"

    def test_substring_still_matches(self):
        # "г. Алматы" (with a prefix) should still resolve to Almaty.
        res = calc.resolve(CountryCode.KZ, "г. Алматы")
        assert res.matched_key == "Алматы"
        assert res.recognized is True


class TestRouteRegression:
    BASE = {
        "rooms": [
            {"room_type": "living_room", "area_m2": 20},
            {"room_type": "kitchen", "area_m2": 10},
            {"room_type": "bathroom", "area_m2": 5},
            {"room_type": "toilet", "area_m2": 2},
            {"room_type": "hallway", "area_m2": 6},
        ],
        "floors": 1,
        "building_shape": "rectangular",
    }

    def test_russia_plus_almaty_currency_and_seismic(self):
        r = client.post("/api/v1/generate-plan", json={**self.BASE, "country": "RU", "region": "Алматы"})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["geo_climate"]["seismic_zone"] == 4
        # Currency follows the effective country (KZ), not the picked RU.
        assert body["cost_estimate"]["currency"] == "KZT"
        assert not any("recognized" in w.lower() for w in body["warnings"])

    def test_unrecognized_region_warns(self):
        r = client.post("/api/v1/generate-plan", json={**self.BASE, "country": "KZ", "region": "Атлантида"})
        assert r.status_code == 200, r.text[:300]
        warnings = r.json()["warnings"]
        assert any("Атлантида" in w for w in warnings), warnings

    def test_unlisted_high_seismic_town_fails_loud_not_low(self):
        # Кордай (near Almaty, genuinely high seismic) isn't in the table → it
        # falls back to KZ's country-average zone 2 (reads LOW). The result must
        # flag the seismicity as unverified so the low number never looks trusted.
        r = client.post("/api/v1/generate-plan", json={**self.BASE, "country": "KZ", "region": "Кордай"})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["region_recognized"] is False

    def test_recognized_region_is_verified(self):
        r = client.post("/api/v1/generate-plan", json={**self.BASE, "country": "KZ", "region": "Алматы"})
        assert r.json()["region_recognized"] is True
