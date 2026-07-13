"""
Plan invariants — the source of truth for "is this floor plan correct".

Seven rules, each checked over the full multi-floor plan. Generation and (later)
every manual edit must leave all seven satisfied. Rules that cannot apply on a
given floor (e.g. circulation rules on an upper floor with no hallway) are
skipped there rather than forced.

  1. No overlaps and no gaps — rooms tile each floor.
  2. Areas respected — no room shrunk below the requested area.
  3. Every room has an opening (a door).
  4. No transit through a private room (bedroom) to reach circulation.
  5. Wet zones share one riser — wet rooms form a single connected cluster.
  6. Entrance through a buffer — the external door belongs to the hallway
     (a garage vehicle gate is exempt: the garage is its own unheated buffer).
  7. Wet-over-wet — an upper-floor wet room sits above a lower-floor wet room.
  8. Mandatory composition — the home has a kitchen and a bathroom/toilet.
  9. Minimum dimension — a room is wide enough for its furniture, not just its
     area (a 12m² room shaped 7.0×1.7m is "correct" on area yet unusable).
 10. Garage buffer — the garage connects to the house only through a
     transitional/service zone (hallway/utility/kitchen/living), never a direct
     door into a bedroom, bathroom, or toilet, and never only through one.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.layout_engine import USABLE_MIN_SIDE, _adjacent_rooms, _door_target, _shared_len
from models import RoomLayout, RoomType

PRIVATE = {RoomType.BEDROOM}
WET = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET}
BUFFER = {RoomType.HALLWAY}
# A vehicle gate is not the pedestrian entrance — the garage is itself an
# unheated buffer, so rule 6 lets it keep an external door.
EXT_DOOR_OK = BUFFER | {RoomType.GARAGE}
# Rule 10 — the garage may connect to the house only through a transitional /
# service zone; a direct door into a bedroom or wet room is a hygiene defect.
#   TRUE buffer (hallway/utility/mudroom) → clean, the intended entry.
#   SOFT buffer (kitchen/living) → allowed but not ideal (fumes into the
#     cooking/living zone), so it ships an honest WARNING, not a silent green.
#   FORBIDDEN (bedroom/bath/toilet) → ERROR.
GARAGE_TRUE_BUFFER = {RoomType.HALLWAY, RoomType.UTILITY}
GARAGE_SOFT_BUFFER = {RoomType.KITCHEN, RoomType.LIVING_ROOM}
GARAGE_FORBIDDEN = PRIVATE | {RoomType.BATHROOM, RoomType.TOILET}

# Rule 9 reads the same usable-minimum table the layout engine sizes bands from,
# so the checker and the generator can never disagree about what "too narrow" is.
MIN_DIMENSION = USABLE_MIN_SIDE

OVERLAP_TOL = 0.02
COVERAGE_MIN = 0.90
AREA_MIN_FRAC = 0.90
FOOTPRINT_OVERLAP_MIN = 0.5  # m² of stacked overlap needed for "wet over wet"
WALLS = ("S", "N", "W", "E")


@dataclass
class Violation:
    rule: int
    code: str
    message: str
    room_id: str | None = None
    # Most invariants are hard failures (ERROR). A few are "allowed but not
    # ideal" (WARNING) — e.g. a garage that reaches the house through the kitchen
    # instead of a mudroom buffer: honest amber, never a silent green.
    severity: str = "ERROR"


def _overlaps(a: RoomLayout, b: RoomLayout) -> bool:
    return (
        a.x < b.x + b.width - OVERLAP_TOL
        and a.x + a.width > b.x + OVERLAP_TOL
        and a.y < b.y + b.depth - OVERLAP_TOL
        and a.y + a.depth > b.y + OVERLAP_TOL
    )


def _stacked_overlap(a: RoomLayout, b: RoomLayout) -> float:
    """Footprint overlap area between two rooms ignoring their floor."""
    dx = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    dy = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    return dx * dy


def _door_graph(rooms: list[RoomLayout]) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {r.room_id: set() for r in rooms}
    for r in rooms:
        for d in r.doors:
            for other in _adjacent_rooms(r, d.wall, rooms):
                edges[r.room_id].add(other.room_id)
                edges[other.room_id].add(r.room_id)
    return edges


def _reachable(edges: dict[str, set[str]], start: str, blocked: set[str]) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for n in edges[stack.pop()]:
            if n not in seen and n not in blocked:
                seen.add(n)
                stack.append(n)
    return seen


def _wet_clusters(wet: list[RoomLayout]) -> int:
    """Number of connected components among wet rooms (via shared walls)."""
    seen: set[str] = set()
    clusters = 0
    for room in wet:
        if room.room_id in seen:
            continue
        clusters += 1
        stack = [room]
        seen.add(room.room_id)
        while stack:
            cur = stack.pop()
            for other in wet:
                if other.room_id not in seen and _shared_len(cur, other) > 0.05:
                    seen.add(other.room_id)
                    stack.append(other)
    return clusters


def check_invariants(
    rooms: list[RoomLayout],
    openness: str = "closed",
    silhouette_m2: float | None = None,
) -> list[Violation]:
    v: list[Violation] = []
    floors = sorted({r.floor for r in rooms})
    by_floor = {f: [r for r in rooms if r.floor == f] for f in floors}
    # Open/mixed move the kitchen into the social zone, so it no longer has to sit
    # on the bath/toilet riser (rule 5). The entry buffer (rule 6) now exists in
    # every mode — in "open" the hallway is opened up, not removed — so rule 6 is
    # no longer skipped.
    wet_types = WET - {RoomType.KITCHEN} if openness != "closed" else WET

    for f, fr in by_floor.items():
        # Rule 1 — overlaps + gaps
        for i in range(len(fr)):
            for j in range(i + 1, len(fr)):
                if _overlaps(fr[i], fr[j]):
                    v.append(
                        Violation(
                            1, "overlap", f'"{fr[i].name}" overlaps "{fr[j].name}"', fr[i].room_id
                        )
                    )
        if fr:
            min_x, min_y = min(r.x for r in fr), min(r.y for r in fr)
            bbox = (max(r.x + r.width for r in fr) - min_x) * (
                max(r.y + r.depth for r in fr) - min_y
            )
            # A non-rectangular silhouette (the L) covers its own declared
            # outline, not its bounding box — judged against the bbox a
            # healthy L reads as a floor full of gaps.
            denom = silhouette_m2 if silhouette_m2 else bbox
            covered = sum(r.width * r.depth for r in fr)
            if denom > 0 and covered < COVERAGE_MIN * denom:
                v.append(Violation(1, "gap", f"floor {f} has {denom - covered:.1f}m² of gaps"))

        # Rule 2 — areas respected. Judged on USABLE metres when the net
        # annotation is present («12 м²» means 12 to live in); axis fallback
        # keeps old stored results and un-annotated callers on the legacy
        # behaviour. Hallways are exempt: circulation prints its real figure
        # by design (its area_m2 may BE the axis figure, not a user request).
        for r in fr:
            if r.room_type == RoomType.HALLWAY:
                continue
            actual = r.net_area if r.net_area is not None else r.width * r.depth
            if actual < r.area_m2 * AREA_MIN_FRAC:
                v.append(
                    Violation(
                        2,
                        "area",
                        f'"{r.name}" is smaller than requested {r.area_m2:.0f}m²',
                        r.room_id,
                    )
                )

        # Rule 3 — every room has a door
        for r in fr:
            if not r.doors:
                v.append(Violation(3, "no_door", f'"{r.name}" has no door', r.room_id))

        # Rule 9 — minimum usable dimension per room type
        for r in fr:
            min_side = MIN_DIMENSION.get(r.room_type, 1.5)
            if min(r.width, r.depth) < min_side - 0.01:
                v.append(
                    Violation(
                        9,
                        "narrow",
                        f'"{r.name}" is only {min(r.width, r.depth):.2f}m wide '
                        f"(needs {min_side:.1f}m) — furniture will not fit",
                        r.room_id,
                    )
                )

        buffer_room = next((r for r in fr if r.room_type in BUFFER), None)

        # Rule 4 — no transit through a private room (only meaningful with a buffer)
        if buffer_room:
            edges = _door_graph(fr)
            private_ids = {r.room_id for r in fr if r.room_type in PRIVATE}
            reached = _reachable(edges, buffer_room.room_id, private_ids)
            for r in fr:
                if r.room_type not in PRIVATE and r.room_id not in reached:
                    v.append(
                        Violation(
                            4,
                            "private_transit",
                            f'"{r.name}" is only reachable through a bedroom',
                            r.room_id,
                        )
                    )

        # Rule 5 — wet zones share one riser (single cluster)
        wet = [r for r in fr if r.room_type in wet_types]
        if _wet_clusters(wet) > 1:
            v.append(
                Violation(
                    5,
                    "wet_split",
                    f"floor {f}: wet rooms are split across {_wet_clusters(wet)} clusters — they cannot share one riser",
                )
            )

        # Rule 6 — entrance through a buffer (ground floor only). The buffer
        # exists in every openness mode now, so this always applies.
        if f == floors[0]:
            for r in fr:
                ext = [w for w in WALLS if not _adjacent_rooms(r, w, fr)]
                has_ext_door = any(d.wall in ext for d in r.doors)
                if has_ext_door and r.room_type not in EXT_DOOR_OK:
                    v.append(
                        Violation(
                            6,
                            "entrance_buffer",
                            f'entrance opens directly into "{r.name}" instead of a hallway',
                            r.room_id,
                        )
                    )

        # Rule 10 — garage connects to the house only through a buffer
        for g in fr:
            if g.room_type is not RoomType.GARAGE:
                continue
            interior = [d for d in g.doors if getattr(d, "kind", "door") != "gate"]
            targets = [t for d in interior if (t := _door_target(g, d, fr))]
            bad = next((t for t in targets if t.room_type in GARAGE_FORBIDDEN), None)
            soft = next((t for t in targets if t.room_type in GARAGE_SOFT_BUFFER), None)
            if bad is not None:
                v.append(
                    Violation(
                        10,
                        "garage_direct",
                        f'garage opens directly into "{bad.name}" — route it through '
                        f"a mudroom / utility buffer instead",
                        g.room_id,
                    )
                )
            elif any(t.room_type in GARAGE_TRUE_BUFFER for t in targets):
                pass  # ideal — a real mudroom/hallway/utility buffer
            elif soft is not None:
                v.append(
                    Violation(
                        10,
                        "garage_soft_buffer",
                        f'garage reaches the house through "{soft.name}" with no mudroom '
                        f"buffer — allowed but not ideal (exhaust/dirt into a living zone)",
                        g.room_id,
                        severity="WARNING",
                    )
                )
            elif not targets:
                # No interior door: if every interior neighbour is a private/wet
                # room, the garage can only reach the house through one — flag it.
                neighbours = [n for w in WALLS for n in _adjacent_rooms(g, w, fr)]
                if neighbours and all(n.room_type in GARAGE_FORBIDDEN for n in neighbours):
                    v.append(
                        Violation(
                            10,
                            "garage_no_buffer",
                            "garage can only reach the house through a bedroom or "
                            "bathroom — add a mudroom / utility buffer",
                            g.room_id,
                        )
                    )

    # Rule 8 — mandatory composition (building-wide)
    types = {r.room_type for r in rooms}
    if RoomType.KITCHEN not in types:
        v.append(Violation(8, "no_kitchen", "the home has no kitchen", None))
    if not (types & {RoomType.BATHROOM, RoomType.TOILET}):
        v.append(Violation(8, "no_bathroom", "the home has no bathroom or toilet", None))

    # Rule 7 — wet-over-wet across floors
    for fi in range(1, len(floors)):
        lower = [r for r in by_floor[floors[fi - 1]] if r.room_type in WET]
        upper = [r for r in by_floor[floors[fi]] if r.room_type in WET]
        for u in upper:
            if not any(_stacked_overlap(u, low) >= FOOTPRINT_OVERLAP_MIN for low in lower):
                v.append(
                    Violation(
                        7,
                        "wet_stack",
                        f'"{u.name}" on floor {floors[fi]} is not above a wet room below it',
                        u.room_id,
                    )
                )

    return v
