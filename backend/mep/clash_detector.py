"""
Clash detection for sketch-level MEP.

At this fidelity the only actionable plumbing problem is a drain/supply line
forced to run through a dry room because a wet room sits far from the riser.
Pipe-to-pipe proximity at the shared riser is expected (that is what a riser is)
and is deliberately NOT reported — flagging it produced noise that no reasonable
edit could clear and undermined trust in the result.
"""

import uuid

from mep.pipe_router import FLOOR_HEIGHT, Pipe
from models import MEPConflict, RoomLayout, RoomType

# Only a pipe over a living space is a problem worth flagging. Crossing a
# hallway, utility room or garage is normal and is left silent.
HABITABLE = {RoomType.LIVING_ROOM, RoomType.BEDROOM}


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
                    if (
                        room.x < mx < room.x + room.width
                        and room.y < my < room.y + room.depth
                    ):
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

        return conflicts
