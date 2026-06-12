import math

import pytest

from core.geo_calculator import (
    GeoClimateCalculator,
    foundation_type_by_frost,
    insulation_by_frost,
    wall_thickness_by_frost,
)
from models import CountryCode

calc = GeoClimateCalculator()


class TestFrostDepth:
    def test_afi_formula_ru_default(self):
        geo = calc.calculate(CountryCode.RU, None, 1)
        assert geo.frost_depth_m == round(0.026 * math.sqrt(2800), 2)  # 1.38

    def test_warm_region_shallower_than_cold(self):
        krasnodar = calc.calculate(CountryCode.RU, "Краснодар", 1)
        siberia = calc.calculate(CountryCode.RU, "Сибирь", 1)
        assert krasnodar.frost_depth_m < siberia.frost_depth_m

    def test_region_substring_match(self):
        # Region matching is case-insensitive substring in both directions
        geo = calc.calculate(CountryCode.KZ, "г. Алматы", 1)
        assert geo.seismic_zone == 4


class TestSeismicLimits:
    @pytest.mark.parametrize(
        "country,region,expected_zone,expected_max_floors",
        [
            (CountryCode.RU, None, 1, 5),
            (CountryCode.KZ, None, 2, 4),
            (CountryCode.KZ, "Алматы", 4, 2),
            (CountryCode.UZ, "Ташкент", 4, 2),
            (CountryCode.US, "California", 4, 2),
        ],
    )
    def test_zone_to_floor_limit(self, country, region, expected_zone, expected_max_floors):
        geo = calc.calculate(country, region, 1)
        assert geo.seismic_zone == expected_zone
        assert geo.max_floors_seismic == expected_max_floors

    def test_high_seismic_forces_antiseismic_foundation(self):
        geo = calc.calculate(CountryCode.KZ, "Алматы", 1)
        assert "антисейсмическая" in geo.foundation_type


class TestThresholds:
    @pytest.mark.parametrize(
        "frost,expected_wall",
        [(0.3, 250), (0.5, 380), (1.19, 380), (1.2, 510), (1.99, 510), (2.0, 640)],
    )
    def test_wall_thickness_boundaries(self, frost, expected_wall):
        assert wall_thickness_by_frost(frost) == expected_wall

    @pytest.mark.parametrize(
        "frost,expected",
        [(0.3, 50), (0.8, 100), (1.5, 150), (2.5, 200)],
    )
    def test_insulation_boundaries(self, frost, expected):
        assert insulation_by_frost(frost) == expected

    def test_foundation_progression_with_frost(self):
        # Low-seismic zones: foundation deepens as frost depth grows
        kinds = [foundation_type_by_frost(f, 1) for f in (0.5, 1.0, 2.0, 3.0)]
        assert kinds == [
            "мелкозаглублённый ленточный",
            "ленточный заглублённый",
            "свайно-ростверковый",
            "буронабивные сваи (глубокое промерзание)",
        ]


class TestSupportedCountries:
    def test_all_country_codes_present(self):
        codes = {c["code"] for c in calc.supported_countries()}
        assert codes == {c.value for c in CountryCode}

    def test_default_not_listed_as_region(self):
        for c in calc.supported_countries():
            assert "default" not in c["regions"]

    def test_unknown_country_falls_back_to_other(self):
        other = calc.calculate(CountryCode.OTHER, None, 1)
        assert other.frost_depth_m > 0
        assert other.max_floors_seismic >= 1
