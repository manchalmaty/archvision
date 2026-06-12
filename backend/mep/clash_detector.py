"""
Clash detection: finds intersections between pipes and structural elements.
"""

import math
import uuid

from mep.pipe_router import Pipe
from models import MEPConflict, RoomLayout

CLASH_RADIUS = 0.15  # metres — minimum clearance


def segment_min_distance(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    q1: tuple[float, float, float],
    q2: tuple[float, float, float],
) -> float:
    """Minimum distance between two 3D line segments."""
    d1 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    d2 = (q2[0] - q1[0], q2[1] - q1[1], q2[2] - q1[2])
    r = (p1[0] - q1[0], p1[1] - q1[1], p1[2] - q1[2])

    a = sum(x * x for x in d1)
    e = sum(x * x for x in d2)
    f = sum(d2[i] * r[i] for i in range(3))

    if a < 1e-10 and e < 1e-10:
        return math.sqrt(sum(x * x for x in r))
    if a < 1e-10:
        s = 0
        t = max(0, min(1, f / e))
    else:
        c = sum(d1[i] * r[i] for i in range(3))
        if e < 1e-10:
            t = 0
            s = max(0, min(1, -c / a))
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            denom = a * e - b * b
            if abs(denom) > 1e-10:
                s = max(0, min(1, (b * f - c * e) / denom))
            else:
                s = 0
            t = (b * s + f) / e
            if t < 0:
                t = 0
                s = max(0, min(1, -c / a))
            elif t > 1:
                t = 1
                s = max(0, min(1, (b - c) / a))

    pt1 = (p1[0] + s * d1[0], p1[1] + s * d1[1], p1[2] + s * d1[2])
    pt2 = (q1[0] + t * d2[0], q1[1] + t * d2[1], q1[2] + t * d2[2])
    return math.sqrt(sum((pt1[i] - pt2[i]) ** 2 for i in range(3)))


class ClashDetector:
    def __init__(self, rooms: list[RoomLayout], pipes: list[Pipe]):
        self.rooms = rooms
        self.pipes = pipes

    def detect(self) -> list[MEPConflict]:
        conflicts = []

        # Pipe–pipe clashes
        for i, pipe_a in enumerate(self.pipes):
            for j, pipe_b in enumerate(self.pipes):
                if j <= i:
                    continue
                for k in range(len(pipe_a.points) - 1):
                    for m in range(len(pipe_b.points) - 1):
                        dist = segment_min_distance(
                            pipe_a.points[k],
                            pipe_a.points[k + 1],
                            pipe_b.points[m],
                            pipe_b.points[m + 1],
                        )
                        min_clearance = (
                            pipe_a.diameter_mm + pipe_b.diameter_mm
                        ) / 2000 + CLASH_RADIUS
                        if dist < min_clearance:
                            mid = (
                                (pipe_a.points[k][0] + pipe_a.points[k + 1][0]) / 2,
                                (pipe_a.points[k][1] + pipe_a.points[k + 1][1]) / 2,
                                (pipe_a.points[k][2] + pipe_a.points[k + 1][2]) / 2,
                            )
                            conflicts.append(
                                MEPConflict(
                                    conflict_id=str(uuid.uuid4()),
                                    conflict_type="pipe_pipe_clash",
                                    description=(
                                        f"Pipe {pipe_a.pipe_type} conflicts with "
                                        f"pipe {pipe_b.pipe_type}: clearance {dist:.2f}m < {min_clearance:.2f}m"
                                    ),
                                    location_x=mid[0],
                                    location_y=mid[1],
                                    location_z=mid[2],
                                    severity="HIGH" if dist < min_clearance * 0.5 else "MEDIUM",
                                )
                            )

        # Structural clash: pipe passes through wall center line
        for pipe in self.pipes:
            for room in self.rooms:
                z_floor = (room.floor - 1) * 3.0
                z_ceil = z_floor + 3.0
                for k in range(len(pipe.points) - 1):
                    px, py, pz = pipe.points[k]
                    # Check if pipe segment is inside room wall zone
                    if (
                        room.x - 0.1 <= px <= room.x + room.width + 0.1
                        and room.y - 0.1 <= py <= room.y + room.depth + 0.1
                        and z_floor <= pz <= z_ceil
                    ):
                        # Check if pipe is ON a wall (not interior)
                        on_wall = (
                            abs(px - room.x) < 0.1
                            or abs(px - (room.x + room.width)) < 0.1
                            or abs(py - room.y) < 0.1
                            or abs(py - (room.y + room.depth)) < 0.1
                        )
                        if on_wall:
                            conflicts.append(
                                MEPConflict(
                                    conflict_id=str(uuid.uuid4()),
                                    conflict_type="pipe_wall_penetration",
                                    description=(
                                        f"{pipe.pipe_type} pipe penetrates wall of {room.name} — add sleeve"
                                    ),
                                    location_x=px,
                                    location_y=py,
                                    location_z=pz,
                                    severity="LOW",
                                )
                            )

        return conflicts
