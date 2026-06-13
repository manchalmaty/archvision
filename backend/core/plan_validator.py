"""
Deterministic geometry validator for LLM-generated floor plans.
Source of truth — the LLM never validates its own output.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

MIN_AREA: dict[str, float] = {
    "bathroom": 2.5,
    "toilet": 1.2,
    "bedroom": 9.0,
    "kitchen": 6.0,
    "living_room": 12.0,
    "hallway": 3.0,
    "utility": 2.0,
    "garage": 12.0,
}

MIN_DIM = 0.9  # no room narrower than 90 cm
OVERLAP_TOL = 0.02  # 2 cm tolerance — shared walls are fine
WALL_TOL = 0.06  # two edges within 6 cm count as the same wall
TOUCH_MIN = 0.30  # min shared-wall length to count rooms as contiguous (m)
DOOR_MIN = 0.75  # min shared-wall length for a door to fit through (m)
COVERAGE_MIN = 0.90  # rooms must cover >=90% of their bounding box (no gaps)


@dataclass
class PlanRoom:
    id: str
    type: str
    name: str
    x: float
    y: float
    w: float
    h: float


def _overlaps(a: PlanRoom, b: PlanRoom) -> bool:
    return (
        a.x < b.x + b.w - OVERLAP_TOL
        and a.x + a.w > b.x + OVERLAP_TOL
        and a.y < b.y + b.h - OVERLAP_TOL
        and a.y + a.h > b.y + OVERLAP_TOL
    )


def _shared_wall_len(a: PlanRoom, b: PlanRoom) -> float:
    """Length of the wall segment two rooms share (0 if they don't touch)."""
    # Vertical wall: a's right edge meets b's left edge (or vice versa)
    if abs(a.x + a.w - b.x) < WALL_TOL or abs(b.x + b.w - a.x) < WALL_TOL:
        return max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    # Horizontal wall: a's bottom edge meets b's top edge (or vice versa)
    if abs(a.y + a.h - b.y) < WALL_TOL or abs(b.y + b.h - a.y) < WALL_TOL:
        return max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    return 0.0


def _reachable(rooms: list[PlanRoom], start_idx: int, min_share: float) -> set[int]:
    """BFS over rooms connected by a shared wall of at least `min_share` metres."""
    seen = {start_idx}
    queue = deque([start_idx])
    while queue:
        i = queue.popleft()
        for j in range(len(rooms)):
            if j in seen:
                continue
            if _shared_wall_len(rooms[i], rooms[j]) >= min_share:
                seen.add(j)
                queue.append(j)
    return seen


def validate_plan(
    rooms: list[PlanRoom],
    fw: float,
    fh: float,
    shape: str = "rectangular",
) -> tuple[list[str], int]:
    """Return (errors, score 0-100). Score = max(0, 100 - 12*error_count)."""
    errors: list[str] = []

    # 1. Room-to-room overlaps
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            if _overlaps(rooms[i], rooms[j]):
                errors.append(f'Rooms "{rooms[i].id}" and "{rooms[j].id}" overlap.')

    # 2. Outside footprint
    for r in rooms:
        if r.x < -0.01 or r.y < -0.01 or r.x + r.w > fw + 0.01 or r.y + r.h > fh + 0.01:
            errors.append(
                f'Room "{r.id}" ({r.type}) extends outside {fw:.1f}×{fh:.1f}m footprint.'
            )

    # 3. Minimum area per type
    for r in rooms:
        min_a = MIN_AREA.get(r.type)
        if min_a and r.w * r.h < min_a - 0.05:
            errors.append(
                f'Room "{r.id}" ({r.type}) is {r.w * r.h:.1f}m², min is {min_a}m².'
            )

    # 4. Minimum dimension (no room narrower than 90 cm)
    for r in rooms:
        if r.w < MIN_DIM or r.h < MIN_DIM:
            errors.append(
                f'Room "{r.id}" dimension {r.w:.2f}×{r.h:.2f}m is too narrow (min {MIN_DIM}m).'
            )

    # Geometry checks below only make sense once basic placement is sane.
    no_overlap_or_oob = len(errors) == 0
    if rooms and no_overlap_or_oob:
        # 5. Coverage — rooms must tile their bounding box (catches gaps / floating rooms)
        min_x = min(r.x for r in rooms)
        min_y = min(r.y for r in rooms)
        bbox_w = max(r.x + r.w for r in rooms) - min_x
        bbox_h = max(r.y + r.h for r in rooms) - min_y
        bbox_area = bbox_w * bbox_h
        covered = sum(r.w * r.h for r in rooms)
        # L/U/T footprints legitimately leave the bbox partly empty; only enforce
        # full tiling for solid rectangular/square plans.
        if shape in ("rectangular", "square") and bbox_area > 0:
            if covered < COVERAGE_MIN * bbox_area:
                gap = bbox_area - covered
                errors.append(
                    f"Plan has {gap:.1f}m² of gaps: rooms cover {covered:.1f}m² but span a "
                    f"{bbox_w:.1f}×{bbox_h:.1f}m area. Rooms must tile the footprint edge to edge."
                )

        # 6. Circulation — every room reachable from the hallway through a door-wide wall
        hall_idx = next((i for i, r in enumerate(rooms) if r.type == "hallway"), None)
        if hall_idx is not None:
            reachable = _reachable(rooms, hall_idx, DOOR_MIN)
            for i, r in enumerate(rooms):
                if i not in reachable:
                    errors.append(
                        f'Room "{r.id}" ({r.type}) is not reachable from the hallway — '
                        f"it needs a shared wall of at least {DOOR_MIN}m with the circulation path."
                    )
        else:
            # No hallway: at least require the plan to be one connected blob
            connected = _reachable(rooms, 0, TOUCH_MIN)
            for i, r in enumerate(rooms):
                if i not in connected:
                    errors.append(
                        f'Room "{r.id}" ({r.type}) is disconnected — it shares no wall with the rest.'
                    )

    score = max(0, 100 - len(errors) * 12)
    return errors, score
