"""
Bill of materials and cost estimation from room layouts.

Sketch-level but physically honest: concrete is the strip foundation plus floor
slabs (not solid concrete partitions everywhere), walls are brick/block at their
real thickness, and shared interior walls are counted once — not once per room.
"""

from models import CostEstimate, CountryCode, GeoClimateData, RoomLayout

FLOOR_HEIGHT = 3.0
SLAB_THICKNESS = 0.2  # m — floor/ceiling slab
INTERIOR_WALL_T = 0.12  # m — partition thickness (exterior comes from geo)
EXT_SOLID_FRAC = 0.70  # exterior wall minus window/door openings
INT_SOLID_FRAC = 0.85  # interior wall minus doorways
LOAD_BEARING_FRAC = 0.5  # share of interior walls that sit on the foundation
STRIP_WIDTH = 0.4  # m — foundation strip footing width
STRIP_BELOW_FROST = 0.2  # m — footing sits this far below the frost line

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


def _floor_walls(rooms: list[RoomLayout]) -> tuple[float, float]:
    """Return (exterior perimeter, interior wall length) for one floor.

    Interior walls are shared between two rooms, so summing per-room perimeters
    double-counts them: interior length = (Σ room perimeters − exterior) / 2.
    """
    if not rooms:
        return 0.0, 0.0
    min_x = min(r.x for r in rooms)
    min_y = min(r.y for r in rooms)
    max_x = max(r.x + r.width for r in rooms)
    max_y = max(r.y + r.depth for r in rooms)
    exterior = 2 * ((max_x - min_x) + (max_y - min_y))
    room_perims = sum(2 * (r.width + r.depth) for r in rooms)
    interior = max(0.0, (room_perims - exterior) / 2)
    return exterior, interior


class CostEstimator:
    def __init__(self, rooms: list[RoomLayout], geo: GeoClimateData, country: CountryCode):
        self.rooms = rooms
        self.geo = geo
        self.country = country

    def estimate(self) -> CostEstimate:
        ext_t = self.geo.wall_thickness_mm / 1000.0
        floors = sorted({r.floor for r in self.rooms}) or [1]

        # Walls (brick/block) and exterior insulation, summed per floor.
        brick_m3 = 0.0
        insulation_m2 = 0.0
        for f in floors:
            ext, interior = _floor_walls([r for r in self.rooms if r.floor == f])
            brick_m3 += ext * FLOOR_HEIGHT * ext_t * EXT_SOLID_FRAC
            brick_m3 += interior * FLOOR_HEIGHT * INTERIOR_WALL_T * INT_SOLID_FRAC
            insulation_m2 += ext * FLOOR_HEIGHT

        # Concrete = strip foundation (ground floor only) + one slab per floor.
        ground_ext, ground_int = _floor_walls([r for r in self.rooms if r.floor == floors[0]])
        strip_length = ground_ext + ground_int * LOAD_BEARING_FRAC
        strip_depth = self.geo.frost_depth_m + STRIP_BELOW_FROST
        foundation_m3 = strip_length * STRIP_WIDTH * strip_depth

        slab_area = sum(r.width * r.depth for r in self.rooms)
        slab_m3 = slab_area * SLAB_THICKNESS
        concrete_total = foundation_m3 + slab_m3

        # Costs
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
