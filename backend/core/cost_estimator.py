"""
Bill of materials and cost estimation from room layouts.
"""

import math

from models import CostEstimate, CountryCode, GeoClimateData, RoomLayout

FLOOR_HEIGHT = 3.0
SLAB_THICKNESS = 0.2

# Material unit costs USD/m3 or USD/m2
MATERIAL_COSTS_USD = {
    "concrete": 120,  # USD/m3
    "brick": 180,  # USD/m3
    "insulation": 15,  # USD/m2
    "steel_rebar": 900,  # USD/tonne (approx 80 kg/m3 concrete → 0.08 t/m3)
    "labor_factor": 0.5,  # 50% of materials for labor
}

# Local currency multipliers relative to USD
CURRENCY_INFO = {
    "RU": ("RUB", 90.0),
    "KZ": ("KZT", 450.0),
    "UA": ("UAH", 38.0),
    "BY": ("BYR", 3.2),
    "UZ": ("UZS", 12700.0),
    "DE": ("EUR", 0.93),
    "US": ("USD", 1.0),
    "OTHER": ("USD", 1.0),
}


class CostEstimator:
    def __init__(self, rooms: list[RoomLayout], geo: GeoClimateData, country: CountryCode):
        self.rooms = rooms
        self.geo = geo
        self.country = country

    def estimate(self) -> CostEstimate:
        wall_t = self.geo.wall_thickness_mm / 1000.0

        total_wall_area = 0.0
        total_slab_area = 0.0
        total_perimeter = 0.0

        for room in self.rooms:
            perimeter = 2 * (room.width + room.depth)
            total_wall_area += perimeter * FLOOR_HEIGHT
            total_slab_area += room.width * room.depth
            total_perimeter += perimeter

        # Concrete: walls + slabs
        wall_concrete_m3 = total_wall_area * wall_t * 0.4  # 40% solid (openings)
        slab_concrete_m3 = total_slab_area * SLAB_THICKNESS

        # Foundation slab
        foundation_area = total_slab_area * 1.1  # 10% overhang
        foundation_concrete_m3 = foundation_area * 0.4

        concrete_total = wall_concrete_m3 + slab_concrete_m3 + foundation_concrete_m3

        # Brick / masonry (outer walls)
        floor_count = max(r.floor for r in self.rooms) if self.rooms else 1
        outer_perimeter = math.sqrt(total_slab_area) * 4 * 0.8  # rough outer perimeter
        brick_m3 = outer_perimeter * FLOOR_HEIGHT * floor_count * wall_t * 0.6

        # Insulation
        insulation_m2 = outer_perimeter * FLOOR_HEIGHT * floor_count

        # Cost calculation
        concrete_cost = concrete_total * MATERIAL_COSTS_USD["concrete"]
        brick_cost = brick_m3 * MATERIAL_COSTS_USD["brick"]
        insulation_cost = insulation_m2 * MATERIAL_COSTS_USD["insulation"]
        rebar_tonnes = concrete_total * 0.08
        rebar_cost = rebar_tonnes * MATERIAL_COSTS_USD["steel_rebar"]

        materials_cost = concrete_cost + brick_cost + insulation_cost + rebar_cost
        labor_cost = materials_cost * MATERIAL_COSTS_USD["labor_factor"]
        total_usd = materials_cost + labor_cost

        currency, rate = CURRENCY_INFO.get(self.country.value, ("USD", 1.0))
        total_local = round(total_usd * rate, 0)

        return CostEstimate(
            concrete_m3=round(concrete_total, 1),
            brick_m3=round(brick_m3, 1),
            insulation_m2=round(insulation_m2, 1),
            total_cost_usd=round(total_usd, 0),
            total_cost_local=total_local,
            currency=currency,
            breakdown={
                "concrete_usd": round(concrete_cost, 0),
                "brick_usd": round(brick_cost, 0),
                "insulation_usd": round(insulation_cost, 0),
                "rebar_usd": round(rebar_cost, 0),
                "labor_usd": round(labor_cost, 0),
            },
        )
