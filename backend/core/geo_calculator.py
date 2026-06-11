"""
Geoclimate calculations for foundation design and structural limits.
Uses Air Freezing Index (AFI) method for frost depth.
"""
import math
from typing import Optional
from models import GeoClimateData, CountryCode

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
    def calculate(
        self, country: CountryCode, region: Optional[str], floors: int
    ) -> GeoClimateData:
        country_data = AFI_BY_COUNTRY.get(country.value, AFI_BY_COUNTRY["OTHER"])

        climate = country_data.get("default", {})
        if region:
            for key in country_data:
                if key.lower() in region.lower() or region.lower() in key.lower():
                    climate = country_data[key]
                    break

        afi = climate["afi"]
        seismic = climate["seismic"]
        snow_kpa = climate["snow_kpa"]
        wind_kpa = climate["wind_kpa"]

        # AFI formula: Z = C * sqrt(AFI), C ≈ 0.026 for clay soils (conservative)
        C = 0.026
        frost_depth_m = round(C * math.sqrt(afi), 2)

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
        )

    def supported_countries(self):
        return [
            {"code": k, "regions": [r for r in v.keys() if r != "default"]}
            for k, v in AFI_BY_COUNTRY.items()
        ]
