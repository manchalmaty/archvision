"""Site placement — the house on its plot (RK setbacks + coverage, v1).

The layout engine draws the *building*; this layer places that building on the
plot and checks it against the rules regional IZHS practice (RK СП, common
across CIS) actually enforces:

  * a street (red-line) setback — the depth of the front yard,
  * a neighbour setback on the other three sides,
  * a maximum plot coverage (building footprint ÷ plot area).

Like the plan invariants this is deterministic and honest: when the requested
program cannot honour a setback on the given plot, that ships as a red SITE-*
issue, never a silent green. The seismic zone is surfaced as an advisory flag
(the floors-vs-seismic limit is already a generation warning) — not a blocker.

Coordinate frame matches the layout engine and renderer: x = west→east,
y = south→north (min-y is the "S"/front/bottom edge). The plan's ground floor
is anchored at the origin; offsets translate it into the plot rectangle.
"""

from __future__ import annotations

from dataclasses import dataclass

from models import RoomLayout, SitePlan

# RK / CIS IZHS practice, rounded to the figures a homeowner is quoted.
STREET_SETBACK_M = 5.0  # to the red line (street)
NEIGHBOR_SETBACK_M = 3.0  # to a neighbour boundary
MAX_COVERAGE = 0.30  # building footprint ÷ plot area
SEISMIC_FLAG_ZONE = 3  # zones ≥ this get the "consult a structural engineer" flag

TOL = 0.01

# Compass edge → the axis and direction it lives on, for centring + clearances.
_EDGES = ("S", "N", "W", "E")


@dataclass
class SiteViolation:
    rule: int
    code: str
    message: str


def _ground_footprint(rooms: list[RoomLayout]) -> tuple[float, float, float, float]:
    """Bounding box (x0, y0, width, depth) of the lowest (ground) floor only.

    Coverage and setbacks are a ground-floor concept — upper floors sit above
    the same footprint, so a larger upstairs never widens the plot footprint.
    """
    if not rooms:
        return 0.0, 0.0, 0.0, 0.0
    ground_floor = min(r.floor for r in rooms)
    ground = [r for r in rooms if r.floor == ground_floor]
    x0 = min(r.x for r in ground)
    y0 = min(r.y for r in ground)
    x1 = max(r.x + r.width for r in ground)
    y1 = max(r.y + r.depth for r in ground)
    return x0, y0, x1 - x0, y1 - y0


def plan_site(
    rooms: list[RoomLayout],
    plot_width: float,
    plot_depth: float,
    street_side: str = "S",
    seismic_zone: int = 1,
) -> SitePlan:
    """Place the building on the plot and return the placement + figures.

    The house is set at the street setback off the street edge and centred
    laterally between the two neighbour edges. Offsets are clamped to keep the
    drawing sane when the program is too big; the shortfall then surfaces as a
    clearance below its required setback (caught by :func:`check_site`).
    """
    street_side = street_side if street_side in _EDGES else "S"
    _, _, bw, bd = _ground_footprint(rooms)

    def clamp(v: float, hi: float) -> float:
        return min(max(v, 0.0), max(hi, 0.0))

    # Place along each axis: front setback off the street edge, centred on the
    # perpendicular axis.
    if street_side in ("S", "N"):
        off_x = clamp((plot_width - bw) / 2.0, plot_width - bw)
        if street_side == "S":
            off_y = clamp(STREET_SETBACK_M, plot_depth - bd)
        else:
            off_y = clamp(plot_depth - STREET_SETBACK_M - bd, plot_depth - bd)
    else:  # "W" | "E"
        off_y = clamp((plot_depth - bd) / 2.0, plot_depth - bd)
        if street_side == "W":
            off_x = clamp(STREET_SETBACK_M, plot_width - bw)
        else:
            off_x = clamp(plot_width - STREET_SETBACK_M - bw, plot_width - bw)

    clearances = {
        "S": round(off_y, 2),
        "N": round(plot_depth - (off_y + bd), 2),
        "W": round(off_x, 2),
        "E": round(plot_width - (off_x + bw), 2),
    }

    plot_area = plot_width * plot_depth
    coverage = (bw * bd) / plot_area if plot_area > 0 else 0.0

    return SitePlan(
        plot_width_m=round(plot_width, 2),
        plot_depth_m=round(plot_depth, 2),
        building_width_m=round(bw, 2),
        building_depth_m=round(bd, 2),
        offset_x=round(off_x, 2),
        offset_y=round(off_y, 2),
        street_side=street_side,
        street_setback_m=STREET_SETBACK_M,
        neighbor_setback_m=NEIGHBOR_SETBACK_M,
        clearances=clearances,
        coverage_ratio=round(coverage, 4),
        coverage_limit=MAX_COVERAGE,
        seismic_zone=seismic_zone,
        seismic_flag=seismic_zone >= SEISMIC_FLAG_ZONE,
    )


_EDGE_NAME = {"S": "Front", "N": "Rear", "W": "Left", "E": "Right"}


def check_site(site: SitePlan) -> list[SiteViolation]:
    """Setback + coverage violations for a placed site plan (honest, no green lie)."""
    violations: list[SiteViolation] = []

    for edge in _EDGES:
        required = site.street_setback_m if edge == site.street_side else site.neighbor_setback_m
        gap = site.clearances[edge]
        if gap < required - TOL:
            kind = "street" if edge == site.street_side else "neighbour"
            violations.append(
                SiteViolation(
                    rule=1,
                    code=edge,
                    message=(
                        f"{_EDGE_NAME[edge]} yard is {gap:.1f} m, below the "
                        f"required {required:.1f} m {kind} setback."
                    ),
                )
            )

    if site.coverage_ratio > site.coverage_limit + TOL:
        violations.append(
            SiteViolation(
                rule=2,
                code="COVERAGE",
                message=(
                    f"Building covers {site.coverage_ratio * 100:.0f}% of the plot, "
                    f"above the {int(site.coverage_limit * 100)}% limit."
                ),
            )
        )

    return violations
