"""
Geoclimate calculations for foundation design and structural limits.
Uses Air Freezing Index (AFI) method for frost depth.
"""

import math
from dataclasses import dataclass

from models import CountryCode, GeoClimateData

# AFI values by country (degree-days Celsius, approximate annual averages)
# Source: climate data aggregated from ASHRAE and national standards
AFI_BY_COUNTRY: dict[str, dict] = {
    "RU": {
        "default": {"afi": 2800, "seismic": 1, "snow_kpa": 2.0, "wind_kpa": 0.38},
        "Москва": {"afi": 2100, "seismic": 1, "snow_kpa": 1.8, "wind_kpa": 0.30},
        "Сибирь": {"afi": 5500, "seismic": 1, "snow_kpa": 3.5, "wind_kpa": 0.42},
        "Краснодар": {"afi": 400, "seismic": 2, "snow_kpa": 0.5, "wind_kpa": 0.45},
        "Владивосток": {"afi": 2200, "seismic": 3, "snow_kpa": 1.5, "wind_kpa": 0.60},
    },
    "KZ": {
        "default": {"afi": 1800, "seismic": 2, "snow_kpa": 1.2, "wind_kpa": 0.55},
        "Алматы": {"afi": 800, "seismic": 4, "snow_kpa": 1.0, "wind_kpa": 0.38},
        "Астана": {"afi": 3200, "seismic": 1, "snow_kpa": 1.5, "wind_kpa": 0.65},
        "Шымкент": {"afi": 600, "seismic": 3, "snow_kpa": 0.4, "wind_kpa": 0.42},
    },
    "UA": {
        "default": {"afi": 800, "seismic": 1, "snow_kpa": 1.2, "wind_kpa": 0.38},
        "Киев": {"afi": 700, "seismic": 1, "snow_kpa": 1.0, "wind_kpa": 0.30},
    },
    "BY": {
        "default": {"afi": 1000, "seismic": 1, "snow_kpa": 1.5, "wind_kpa": 0.30},
    },
    "UZ": {
        "default": {"afi": 300, "seismic": 3, "snow_kpa": 0.3, "wind_kpa": 0.38},
        "Ташкент": {"afi": 250, "seismic": 4, "snow_kpa": 0.2, "wind_kpa": 0.35},
    },
    "DE": {
        "default": {"afi": 200, "seismic": 1, "snow_kpa": 0.8, "wind_kpa": 0.50},
    },
    "US": {
        "default": {"afi": 600, "seismic": 1, "snow_kpa": 1.0, "wind_kpa": 0.48},
        "Alaska": {"afi": 6000, "seismic": 3, "snow_kpa": 5.0, "wind_kpa": 0.55},
        "California": {"afi": 50, "seismic": 4, "snow_kpa": 0.2, "wind_kpa": 0.45},
    },
    "OTHER": {
        "default": {"afi": 500, "seismic": 1, "snow_kpa": 0.5, "wind_kpa": 0.38},
    },
}

# Seismic zone → max allowed floors without special engineering
SEISMIC_FLOOR_LIMITS = {1: 5, 2: 4, 3: 3, 4: 2}

# Zones at/above this need the high-seismicity structural advisory (ж/б каркас /
# монолитный фундамент). On this engine's internal 1–4 scale, 3–4 approximate
# high MSK intensity; the exact site intensity is an ОСР/СНиП map value, NOT
# something this tool asserts.
SEISMIC_ADVISORY_ZONE = 3


@dataclass
class RegionResolution:
    """How a (country, region) request resolved against the region index.

    effective_country is the country whose region actually matched — it may
    differ from the requested country (pick RU, type "Алматы" → KZ), and it is
    what drives the local currency. recognized is False only when a region was
    given but matched nothing, so the caller can flag it instead of silently
    using country-average climate under the city's name.
    """

    effective_country: str
    climate: dict
    matched_key: str | None
    recognized: bool


# Wall thickness rules by frost depth (mm)
def wall_thickness_by_frost(frost_depth_m: float) -> int:
    if frost_depth_m < 0.5:
        return 250
    elif frost_depth_m < 1.2:
        return 380
    elif frost_depth_m < 2.0:
        return 510
    else:
        return 640


def insulation_by_frost(frost_depth_m: float) -> int:
    if frost_depth_m < 0.5:
        return 50
    elif frost_depth_m < 1.2:
        return 100
    elif frost_depth_m < 2.0:
        return 150
    else:
        return 200


def foundation_type_by_frost(frost_depth_m: float, seismic_zone: int) -> str:
    if seismic_zone >= 3:
        return "монолитная плита (антисейсмическая)"
    if frost_depth_m < 0.8:
        return "мелкозаглублённый ленточный"
    elif frost_depth_m < 1.5:
        return "ленточный заглублённый"
    elif frost_depth_m < 2.5:
        return "свайно-ростверковый"
    else:
        return "буронабивные сваи (глубокое промерзание)"


class GeoClimateCalculator:
    def resolve(self, country: CountryCode, region: str | None) -> RegionResolution:
        """Resolve a region name to its climate + effective country, globally.

        Priority: exact match inside the selected country → exact match in any
        country → substring inside the selected country → substring in any
        country. Anything left is unrecognized (recognized=False) and falls back
        to the selected country's average. A region is a real place regardless of
        which country the user picked, so its seismicity/frost must not be masked
        by the picked country's default (the Almaty-under-Russia safety bug).
        """
        cc = country.value
        country_data = AFI_BY_COUNTRY.get(cc, AFI_BY_COUNTRY["OTHER"])
        default = country_data.get("default", {})

        if not region or not region.strip():
            return RegionResolution(cc, default, None, True)
        r = region.strip().lower()

        def regions(data: dict):
            return ((k, v) for k, v in data.items() if k != "default")

        # 1. exact match within the selected country
        for key, val in regions(country_data):
            if key.lower() == r:
                return RegionResolution(cc, val, key, True)
        # 2. exact match in any country → that region's country is effective
        for oc, data in AFI_BY_COUNTRY.items():
            for key, val in regions(data):
                if key.lower() == r:
                    return RegionResolution(oc, val, key, True)
        # 3. substring within the selected country (e.g. "г. Алматы")
        for key, val in regions(country_data):
            if key.lower() in r or r in key.lower():
                return RegionResolution(cc, val, key, True)
        # 4. substring in any country
        for oc, data in AFI_BY_COUNTRY.items():
            for key, val in regions(data):
                if key.lower() in r or r in key.lower():
                    return RegionResolution(oc, val, key, True)
        # 5. unrecognized — flag it, do not pretend
        return RegionResolution(cc, default, None, False)

    def calculate(self, country: CountryCode, region: str | None, floors: int) -> GeoClimateData:
        climate = self.resolve(country, region).climate

        afi = climate["afi"]
        seismic = climate["seismic"]
        snow_kpa = climate["snow_kpa"]
        wind_kpa = climate["wind_kpa"]

        # AFI formula: Z = C * sqrt(AFI), C ≈ 0.026 for clay soils (conservative)
        C = 0.026
        frost_depth_m = round(C * math.sqrt(afi), 2)

        # Design winter temperature from the same index (fit against СП 131
        # anchor cities: Москва −28, Новосибирск −37, Краснодар −19). Draft
        # accuracy ±5 °C — heat loss is linear in ΔT, so a boiler sized with a
        # 25% margin absorbs it; the UI labels the figure as index-derived.
        design_temp_c = -round(5 + 0.45 * math.sqrt(afi))

        wall_mm = wall_thickness_by_frost(frost_depth_m)
        insulation_mm = insulation_by_frost(frost_depth_m)
        foundation = foundation_type_by_frost(frost_depth_m, seismic)
        max_floors = SEISMIC_FLOOR_LIMITS.get(seismic, 5)

        return GeoClimateData(
            frost_depth_m=frost_depth_m,
            foundation_type=foundation,
            seismic_zone=seismic,
            max_floors_seismic=max_floors,
            wall_thickness_mm=wall_mm,
            insulation_thickness_mm=insulation_mm,
            snow_load_kpa=snow_kpa,
            wind_load_kpa=wind_kpa,
            design_temp_c=design_temp_c,
        )

    def supported_countries(self):
        return [
            {"code": k, "regions": [r for r in v.keys() if r != "default"]}
            for k, v in AFI_BY_COUNTRY.items()
        ]
