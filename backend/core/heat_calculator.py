"""Draft heating layer: envelope heat loss by the U-value method + boiler sizing.

Sketch-level but physically honest, like the cost model: the real geo-driven
wall/insulation thicknesses, the same 30% window fraction the cost model
already assumes for openings, ventilation at 0.35 air changes per hour. The
garage is excluded — it is the plan's unheated buffer. NOT a thermal
engineering calculation (СП 50): the figure exists so the boiler and heating
conversation with an engineer starts earlier.
"""

import math

from core.cost_estimator import EXT_SOLID_FRAC, FLOOR_HEIGHT, _floor_walls
from models import GeoClimateData, HeatingEstimate, RoomLayout, RoomType

INDOOR_C = 20.0
LAMBDA_WALL = 0.5  # brick/block, W/mK
LAMBDA_INS = 0.04  # mineral wool, W/mK
R_SURFACES = 0.16  # interior + exterior surface film resistances
U_WINDOW = 1.4  # double-glazed unit
WINDOW_FRAC = 1 - EXT_SOLID_FRAC  # the openings share the cost model prices
ROOF_EXTRA_INS_M = 0.05  # attics carry ~50 mm more than walls
R_SLAB = 0.12  # 200 mm concrete slab
U_FLOOR = 0.4  # ground slab with edge insulation
FLOOR_DT_FACTOR = 0.5  # ground under the slab is far milder than design air
ACH = 0.35  # ventilation air changes per hour
AIR_HEAT_WH = 0.34  # Wh per m³·K of air
BOILER_MARGIN = 1.25


def estimate_heating(rooms: list[RoomLayout], geo: GeoClimateData) -> HeatingEstimate | None:
    if geo.design_temp_c is None:
        return None
    heated = [r for r in rooms if r.room_type != RoomType.GARAGE]
    if not heated:
        return None
    dt = INDOOR_C - geo.design_temp_c

    area = sum(r.width * r.depth for r in heated)
    floors = sorted({r.floor for r in heated})
    ext_wall_area = 0.0
    for f in floors:
        ext, _ = _floor_walls([r for r in heated if r.floor == f])
        ext_wall_area += ext * FLOOR_HEIGHT
    win_area = ext_wall_area * WINDOW_FRAC
    wall_area = ext_wall_area - win_area

    r_wall = (
        geo.wall_thickness_mm / 1000 / LAMBDA_WALL
        + geo.insulation_thickness_mm / 1000 / LAMBDA_INS
        + R_SURFACES
    )
    r_roof = R_SLAB + (geo.insulation_thickness_mm / 1000 + ROOF_EXTRA_INS_M) / LAMBDA_INS
    roof_area = sum(r.width * r.depth for r in heated if r.floor == floors[-1])
    ground_area = sum(r.width * r.depth for r in heated if r.floor == floors[0])
    volume = area * FLOOR_HEIGHT

    w_per_k = (
        wall_area / r_wall
        + win_area * U_WINDOW
        + roof_area / r_roof
        + AIR_HEAT_WH * ACH * volume
    )
    q_w = w_per_k * dt + U_FLOOR * ground_area * dt * FLOOR_DT_FACTOR
    kw = q_w / 1000
    return HeatingEstimate(
        design_temp_c=geo.design_temp_c,
        heated_area_m2=round(area, 1),
        heat_loss_kw=round(kw, 1),
        specific_w_m2=round(q_w / area, 0),
        boiler_kw=float(math.ceil(kw * BOILER_MARGIN)),
    )
