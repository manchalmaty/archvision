"""
Agentic floor-plan layout: Groq generates JSON → deterministic validator checks →
errors fed back → repeat up to MAX_ITER. Falls back to LayoutEngine if no API key.
"""
from __future__ import annotations

import json
import logging
import math
import uuid

from openai import OpenAI

from config import settings
from core.layout_engine import LayoutEngine
from core.plan_validator import PlanRoom, validate_plan
from models import BuildingParams, GeoClimateData, RoomLayout, RoomType

logger = logging.getLogger(__name__)

MAX_ITER = 5

_SYSTEM = """\
You are an architectural layout engine. Output 2D floor plans as strict JSON.
No markdown fences, no prose, no explanations.

Coordinate system: metres, origin top-left, x→right, y→down.
Every room is an axis-aligned rectangle {x, y, w, h}.

HARD RULES (a plan that breaks any of these is rejected and you must redo it):
1. Rooms MUST NOT overlap — not even by 1 cm.
2. Rooms MUST tile the footprint edge to edge — NO gaps, NO empty space between
   rooms. Adjacent rooms share a full wall: one room's edge is exactly another's
   edge. Think of it as cutting a single rectangle into pieces.
3. All rooms fit inside the footprint (x>=0, y>=0, x+w<=fw, y+h<=fh).
4. The hallway sits central and touches every other room along a shared wall of
   at least 0.8 m, so a door fits — EVERY room must be reachable from the hallway.
5. Minimum areas: bedroom≥9, living_room≥12, kitchen≥6, bathroom≥2.5, toilet≥1.2.
6. No room narrower than 0.9 m in either dimension.

LAYOUT GUIDANCE:
- Wet zones (bathroom, toilet, kitchen) grouped together to share plumbing.
- Kitchen on an exterior wall. Bedrooms in the quiet back, away from the entrance.
- Prefer a few clean rows/columns over many tiny offset rectangles.

Worked method: pick the footprint, place the hallway as a central spine, then
fill the remaining strips left/right/above/below with rooms so every strip is
fully consumed and each room borders the hallway.

Output ONLY this JSON — nothing else:
{
  "footprint": {"w": <number>, "h": <number>},
  "rooms": [
    {"id": "<string>", "type": "<type>", "name": "<string>", "x": <m>, "y": <m>, "w": <m>, "h": <m>}
  ]
}
Valid types: hallway living_room bedroom kitchen bathroom toilet utility garage"""


def _get_client() -> OpenAI | None:
    if not settings.GROQ_API_KEY:
        return None
    return OpenAI(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")


def _estimate_footprint(params: BuildingParams, floor_rooms: list) -> tuple[float, float]:
    total = sum(r.area_m2 for r in floor_rooms)
    gross = total * 1.22  # ~22% for walls + circulation
    aspect = 1.3 if params.building_shape in ("rectangular", "l_shape", "t_shape") else 1.0
    w = round(math.sqrt(gross * aspect), 1)
    h = round(gross / max(w, 0.1), 1)
    if params.plot_width_m:
        w = min(w, params.plot_width_m)
    if params.plot_depth_m:
        h = min(h, params.plot_depth_m)
    return max(w, 3.0), max(h, 3.0)


def _build_prompt(floor_num: int, total_floors: int, params: BuildingParams,
                  floor_rooms: list, fw: float, fh: float) -> str:
    room_lines = "\n".join(
        f"  - {r.area_m2:.0f}m²  {r.room_type.value}" + (f" ({r.name})" if r.name else "")
        for r in floor_rooms
    )
    return (
        f"Generate floor {floor_num} of {total_floors}.\n"
        f"Footprint: {fw}m wide × {fh}m deep  (building shape: {params.building_shape})\n"
        f"Country: {params.country.value}\n"
        f"Rooms to place on this floor:\n{room_lines}\n\n"
        "Return the JSON only."
    )


def _parse(text: str) -> tuple[dict, list[PlanRoom]]:
    clean = text.strip()
    # Strip markdown fences if the model added them anyway
    if clean.startswith("```"):
        lines = clean.splitlines()
        clean = "\n".join(line for line in lines if not line.strip().startswith("```"))
    data = json.loads(clean)
    rooms = [
        PlanRoom(
            id=str(r["id"]),
            type=str(r["type"]),
            name=str(r.get("name", r["type"])),
            x=float(r["x"]),
            y=float(r["y"]),
            w=float(r["w"]),
            h=float(r["h"]),
        )
        for r in data["rooms"]
    ]
    return data["footprint"], rooms


def _to_layouts(plan_rooms: list[PlanRoom], floor: int) -> list[RoomLayout]:
    layouts = []
    for r in plan_rooms:
        try:
            rtype = RoomType(r.type)
        except ValueError:
            rtype = RoomType.UTILITY
        layouts.append(
            RoomLayout(
                room_id=str(uuid.uuid4()),
                room_type=rtype,
                name=r.name or rtype.value.replace("_", " ").title(),
                x=round(r.x, 3),
                y=round(r.y, 3),
                floor=floor,
                width=round(r.w, 3),
                depth=round(r.h, 3),
                area_m2=round(r.w * r.h, 2),
            )
        )
    return layouts


def _layout_floor_llm(
    client: OpenAI,
    floor_num: int,
    total_floors: int,
    params: BuildingParams,
    floor_rooms: list,
) -> list[RoomLayout] | None:
    """Try to generate one floor via LLM loop. Returns None on total failure."""
    fw, fh = _estimate_footprint(params, floor_rooms)
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _build_prompt(floor_num, total_floors, params, floor_rooms, fw, fh)},
    ]

    best_layouts: list[RoomLayout] | None = None
    best_err_count = 9999

    for iteration in range(1, MAX_ITER + 1):
        try:
            resp = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                max_tokens=4096,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("Groq call failed floor=%d iter=%d: %s", floor_num, iteration, exc)
            break

        text = resp.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": text})

        try:
            footprint, plan_rooms = _parse(text)
            afw = float(footprint["w"])
            afh = float(footprint["h"])
        except Exception as exc:
            logger.warning("JSON parse error floor=%d iter=%d: %s", floor_num, iteration, exc)
            messages.append({
                "role": "user",
                "content": "Invalid JSON. Return ONLY the JSON object — no markdown, no text.",
            })
            continue

        errors, score = validate_plan(plan_rooms, afw, afh, params.building_shape)
        logger.info("LLM floor=%d iter=%d score=%d errors=%d", floor_num, iteration, score, len(errors))

        layouts = _to_layouts(plan_rooms, floor=floor_num)
        if len(errors) < best_err_count:
            best_err_count = len(errors)
            best_layouts = layouts

        if not errors:
            return layouts, 0

        messages.append({
            "role": "user",
            "content": (
                f"Geometry validator found {len(errors)} problem(s):\n"
                + "\n".join(f"{k + 1}. {e}" for k, e in enumerate(errors))
                + "\n\nFix ALL problems. Return corrected JSON only."
            ),
        })

    # Still has errors → caller will decide whether to fall back
    return best_layouts, best_err_count


class LLMLayoutEngine:
    """
    Drop-in replacement for LayoutEngine.
    Uses Groq LLM to generate spatial layout; falls back to rule-based if key absent.
    """

    def __init__(self, params: BuildingParams, geo: GeoClimateData):
        self.params = params
        self.geo = geo
        self.warnings: list[str] = []
        self._rule = LayoutEngine(params, geo)

    def generate(self) -> list[RoomLayout]:
        client = _get_client()
        if not client:
            logger.info("No GROQ_API_KEY — using rule-based layout")
            result = self._rule.generate()
            self.warnings.extend(self._rule.warnings)
            return result

        # Reuse existing room prep + multi-floor distribution
        rooms = self._rule._ensure_essentials(list(self.params.rooms))
        rooms_per_floor = self._rule._distribute_floors(rooms)

        all_layouts: list[RoomLayout] = []
        for floor_idx, floor_rooms in enumerate(rooms_per_floor):
            floor_num = floor_idx + 1
            if not floor_rooms:
                continue

            result_pair = _layout_floor_llm(client, floor_num, self.params.floors, self.params, floor_rooms)

            if result_pair is None:
                logger.warning("LLM failed floor=%d — falling back to rule-based", floor_num)
                self.warnings.append("LLM layout failed — used rule-based fallback")
                rule_result = self._rule.generate()
                self.warnings.extend(self._rule.warnings)
                return rule_result

            layouts, err_count = result_pair
            if err_count > 0:
                # LLM couldn't produce a clean plan — rule-based is more reliable
                logger.warning(
                    "LLM plan has %d unresolved error(s) on floor=%d — using rule-based",
                    err_count, floor_num,
                )
                self.warnings.append(
                    f"LLM layout had {err_count} geometry issue(s) — used rule-based fallback"
                )
                rule_result = self._rule.generate()
                self.warnings.extend(self._rule.warnings)
                return rule_result

            all_layouts.extend(layouts)

        # Deterministic openings — reuse the rule engine's single source of truth
        self._rule._assign_openings(all_layouts)
        self._rule._check_plot_fit(all_layouts)
        self.warnings.extend(self._rule.warnings)
        return all_layouts
