"""Cost-Δ variant comparison — the decision table behind the spaciousness slider.

The same room program is re-tiled at three FIXED spaciousness settings by the
deterministic rule engine (never the LLM: a table the user acts on must be
reproducible). Each row is priced by the same estimator as the hero figure and
carries an honest ERROR count — a cheaper variant that breaks minimum room
sizes must say so in the same row that tempts with the saving.
"""

import logging

from core.cost_estimator import CostEstimator
from core.layout_engine import LayoutEngine
from core.plan_invariants import check_invariants
from core.site_planner import check_site, plan_site
from models import BuildingParams, CountryCode, GeoClimateData, PlanVariant

logger = logging.getLogger(__name__)

VARIANT_SETTINGS: list[tuple[str, float]] = [
    ("compact", 0.0),
    ("balanced", 0.5),
    ("roomy", 1.0),
]


def build_variants(
    params: BuildingParams, geo: GeoClimateData, country: CountryCode
) -> list[PlanVariant]:
    rows: list[tuple[PlanVariant, dict]] = []
    for label, s in VARIANT_SETTINGS:
        p = params.model_copy(update={"spaciousness": s}, deep=True)
        try:
            engine = LayoutEngine(p, geo)
            rooms = engine.generate()
        except Exception:  # a setting that cannot tile is a missing row, not a 500
            logger.warning("variant %r failed to tile — row skipped", label)
            continue
        red = sum(
            1
            for v in check_invariants(
                rooms, openness=p.openness, silhouette_m2=engine.silhouette_m2
            )
            if v.severity == "ERROR"
        )
        if p.plot_width_m and p.plot_depth_m:
            site = plan_site(rooms, p.plot_width_m, p.plot_depth_m, p.street_side, geo.seismic_zone)
            red += len(check_site(site))
        cost = CostEstimator(rooms, geo, country).estimate()
        variant = PlanVariant(
            label=label,
            spaciousness=s,
            footprint_m2=round(sum(r.width * r.depth for r in rooms), 1),
            concrete_m3=cost.concrete_m3,
            brick_m3=cost.brick_m3,
            total_cost_local=cost.total_cost_local,
            total_cost_usd=cost.total_cost_usd,
            currency=cost.currency,
            red_flags=red,
        )
        rows.append((variant, cost.breakdown))

    rows.sort(key=lambda rb: rb[0].total_cost_local)
    if not rows:
        return []
    base, base_bd = rows[0]
    for variant, bd in rows[1:]:
        variant.delta_local = round(variant.total_cost_local - base.total_cost_local, 0)
        variant.delta_usd = round(variant.total_cost_usd - base.total_cost_usd, 0)
        variant.delta_footprint_m2 = round(variant.footprint_m2 - base.footprint_m2, 1)
        variant.delta_concrete_m3 = round(variant.concrete_m3 - base.concrete_m3, 1)
        # Attribute the delta to its dominant material system. Labor is a fixed
        # fraction of materials, so it can never win on its own.
        d_concrete = (bd["concrete_usd"] - base_bd["concrete_usd"]) + (
            bd["rebar_usd"] - base_bd["rebar_usd"]
        )
        d_walls = (bd["brick_usd"] - base_bd["brick_usd"]) + (
            bd["insulation_usd"] - base_bd["insulation_usd"]
        )
        variant.delta_driver = "concrete" if d_concrete >= d_walls else "walls"
    return [rb[0] for rb in rows]
