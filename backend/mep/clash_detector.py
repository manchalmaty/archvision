"""
Clash detection for sketch-level MEP.

At this fidelity the only actionable plumbing problem is a drain/supply line
forced to run through a dry room because a wet room sits far from the riser.
Pipe-to-pipe proximity at the shared riser is expected (that is what a riser is)
and is deliberately NOT reported — flagging it produced noise that no reasonable
edit could clear and undermined trust in the result.
"""

import math
import uuid

from mep.pipe_router import FLOOR_HEIGHT, WET_ZONES, Pipe, riser_xy
from models import MEPConflict, RoomLayout, RoomType

# Only a pipe over a living space is a problem worth flagging. Crossing a
# hallway, utility room or garage is normal and is left silent.
HABITABLE = {RoomType.LIVING_ROOM, RoomType.BEDROOM}

# A wet room whose centre is farther than this from the riser needs its own long
# branch — a "costly to plumb" advisory, not a hard error.
FAR_FROM_RISER_M = 6.0
WET_STACK_OVERLAP_MIN = 0.5  # m² of footprint overlap to count as "stacked over"


def _overlap_area(a: RoomLayout, b: RoomLayout) -> float:
    dx = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    dy = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    return dx * dy


class ClashDetector:
    def __init__(self, rooms: list[RoomLayout], pipes: list[Pipe]):
        self.rooms = rooms
        self.pipes = pipes

    def detect(self) -> list[MEPConflict]:
        conflicts: list[MEPConflict] = []
        seen: set[tuple[str, str]] = set()  # (room_id, pipe_id) — one report each

        for pipe in self.pipes:
            if pipe.pipe_type == "riser":  # the vertical stack lives in its shaft
                continue
            for k in range(len(pipe.points) - 1):
                a, b = pipe.points[k], pipe.points[k + 1]
                if abs(a[2] - b[2]) > 0.05:  # only horizontal runs cross rooms
                    continue
                mx, my, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2
                floor = int(mz // FLOOR_HEIGHT) + 1
                for room in self.rooms:
                    if room.floor != floor or room.room_type not in HABITABLE:
                        continue
                    if (room.room_id, pipe.pipe_id) in seen:
                        continue
                    if room.x < mx < room.x + room.width and room.y < my < room.y + room.depth:
                        seen.add((room.room_id, pipe.pipe_id))
                        conflicts.append(
                            MEPConflict(
                                conflict_id=str(uuid.uuid4()),
                                conflict_type="pipe_through_room",
                                description=(
                                    f"{pipe.pipe_type} pipe is routed through {room.name} "
                                    f"({room.room_type.value}) — move this wet room next to the "
                                    f"riser or regroup the wet zone"
                                ),
                                location_x=mx,
                                location_y=my,
                                location_z=mz,
                                severity="MEDIUM",
                            )
                        )

        conflicts.extend(self._costly_zones())
        return conflicts

    def _costly_zones(self) -> list[MEPConflict]:
        """Honest draft advisories (not buildable-spec checks): a wet room far
        from the riser needs its own long branch, and a wet room stacked over a
        living space upstairs is a leak risk that is costly to move later."""
        out: list[MEPConflict] = []
        wet = [r for r in self.rooms if r.room_type in WET_ZONES]
        riser = riser_xy(self.rooms)
        if riser:
            rx, ry = riser
            for r in wet:
                cx, cy = r.x + r.width / 2, r.y + r.depth / 2
                dist = math.hypot(cx - rx, cy - ry)
                if dist > FAR_FROM_RISER_M:
                    out.append(
                        MEPConflict(
                            conflict_id=str(uuid.uuid4()),
                            conflict_type="far_from_riser",
                            description=(
                                f"{r.name} is {dist:.1f} m from the riser — needs its own "
                                f"long supply/drain branch (costly). Group the wet rooms or "
                                f"add a second riser."
                            ),
                            location_x=cx,
                            location_y=cy,
                            location_z=(r.floor - 1) * FLOOR_HEIGHT + 0.5,
                            severity="MEDIUM",
                        )
                    )
        for w in wet:
            if w.floor <= 1:
                continue
            for d in self.rooms:
                if d.floor != w.floor - 1 or d.room_type not in HABITABLE:
                    continue
                if _overlap_area(w, d) >= WET_STACK_OVERLAP_MIN:
                    out.append(
                        MEPConflict(
                            conflict_id=str(uuid.uuid4()),
                            conflict_type="wet_over_dry",
                            description=(
                                f"{w.name} (floor {w.floor}) sits above {d.name} — a wet room "
                                f"over a living space. Leak risk and costly to move later; stack "
                                f"it over a wet room instead."
                            ),
                            location_x=w.x + w.width / 2,
                            location_y=w.y + w.depth / 2,
                            location_z=(w.floor - 1) * FLOOR_HEIGHT + 0.5,
                            severity="HIGH",
                        )
                    )
                    break
        return out
