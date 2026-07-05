"""
3D A* pipe routing for MEP (plumbing).
Routes pipes from wet zones to a central riser shaft.
"""

import heapq
import math
import uuid
from dataclasses import dataclass, field
from typing import Optional

from models import GeoClimateData, RoomLayout, RoomType

# Wet points that need plumbing — kitchen, bathroom, toilet, and the laundry
# (utility). Laundry is included so its supply/drain shows up in the draft.
WET_ZONES = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET, RoomType.UTILITY}
GRID_STEP = 0.5  # metres per grid cell
FLOOR_HEIGHT = 3.0  # metres per storey


def riser_xy(rooms: list[RoomLayout]) -> tuple[float, float] | None:
    """The plumbing riser sits at the centre of the largest wet room on the
    lowest wet floor, so drains stay inside the (grouped) wet zone instead of
    crossing bedrooms. Returns None when there are no wet rooms."""
    wet = [r for r in rooms if r.room_type in WET_ZONES]
    if not wet:
        return None
    low_floor = min(r.floor for r in wet)
    anchor = max((r for r in wet if r.floor == low_floor), key=lambda r: r.width * r.depth)
    return (anchor.x + anchor.width / 2, anchor.y + anchor.depth / 2)


@dataclass
class Pipe:
    pipe_id: str
    pipe_type: str  # "supply" | "drain" | "vent"
    points: list[tuple[float, float, float]]
    diameter_mm: int
    from_room_id: str
    to_room_id: str


@dataclass(order=True)
class Node:
    f: float
    g: float = field(compare=False)
    pos: tuple[int, int, int] = field(compare=False)
    parent: Optional["Node"] = field(compare=False, default=None)


def heuristic(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def astar_3d(
    start: tuple[int, int, int],
    goal: tuple[int, int, int],
    obstacles: set,
) -> list[tuple[int, int, int]]:
    open_heap: list = []
    h = heuristic(start, goal)
    start_node = Node(f=h, g=0, pos=start)
    heapq.heappush(open_heap, start_node)
    came_from: dict = {start: None}
    g_score: dict = {start: 0}

    DIRS = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]

    while open_heap:
        current = heapq.heappop(open_heap)
        if current.pos == goal:
            path = []
            node = current
            while node:
                path.append(node.pos)
                node = node.parent
            return list(reversed(path))

        for dx, dy, dz in DIRS:
            nb = (current.pos[0] + dx, current.pos[1] + dy, current.pos[2] + dz)
            if nb in obstacles:
                continue
            # Prefer horizontal routing (penalise vertical)
            step_cost = 1.0 if dz == 0 else 3.0
            tentative_g = g_score[current.pos] + step_cost
            if tentative_g < g_score.get(nb, float("inf")):
                g_score[nb] = tentative_g
                f = tentative_g + heuristic(nb, goal)
                nb_node = Node(f=f, g=tentative_g, pos=nb, parent=current)
                heapq.heappush(open_heap, nb_node)
                came_from[nb] = current.pos

    return []  # no path found


def world_to_grid(x: float, y: float, z: float) -> tuple[int, int, int]:
    return (round(x / GRID_STEP), round(y / GRID_STEP), round(z / GRID_STEP))


def grid_to_world(gx: int, gy: int, gz: int) -> tuple[float, float, float]:
    return (gx * GRID_STEP, gy * GRID_STEP, gz * GRID_STEP)


class PipeRouter:
    def __init__(self, rooms: list[RoomLayout], floors: int, geo: GeoClimateData | None):
        self.rooms = rooms
        self.floors = floors
        self.geo = geo

    def route(self) -> list[Pipe]:
        wet_rooms = [r for r in self.rooms if r.room_type in WET_ZONES]
        if not wet_rooms:
            return []

        # Riser shaft inside the largest wet room (keeps runs within the wet zone)
        riser_x, riser_y = riser_xy(self.rooms)

        obstacles = self._build_obstacles()
        pipes = []

        for room in wet_rooms:
            rx = room.x + room.width / 2
            ry = room.y + room.depth / 2
            floor_base = (room.floor - 1) * 3.0

            # Drain: gravity-fed, runs at floor level (0.5m above slab)
            rz_drain = floor_base + 0.5
            start_drain = world_to_grid(rx, ry, rz_drain)
            goal_drain = world_to_grid(riser_x, riser_y, rz_drain)
            path_drain = astar_3d(start_drain, goal_drain, obstacles)
            if not path_drain:
                path_drain = [start_drain, goal_drain]

            pipes.append(
                Pipe(
                    pipe_id=str(uuid.uuid4()),
                    pipe_type="drain",
                    points=[grid_to_world(*p) for p in path_drain],
                    diameter_mm=110,
                    from_room_id=room.room_id,
                    to_room_id="riser",
                )
            )

            # Supply: pressurised cold water, runs near ceiling (2.2m above slab)
            rz_supply = floor_base + 2.2
            start_supply = world_to_grid(rx, ry, rz_supply)
            goal_supply = world_to_grid(riser_x, riser_y, rz_supply)
            path_supply = astar_3d(start_supply, goal_supply, obstacles)
            if not path_supply:
                path_supply = [start_supply, goal_supply]

            pipes.append(
                Pipe(
                    pipe_id=str(uuid.uuid4()),
                    pipe_type="supply",
                    points=[grid_to_world(*p) for p in path_supply],
                    diameter_mm=25,
                    from_room_id="supply_main",
                    to_room_id=room.room_id,
                )
            )

        # Vertical riser: a single stack tying every wet floor together. Without
        # it, upper-floor drains terminate in mid-air instead of running down to
        # the ground-floor sewer connection.
        wet_floors = sorted({r.floor for r in wet_rooms})
        if len(wet_floors) > 1:
            z_bottom = (wet_floors[0] - 1) * FLOOR_HEIGHT + 0.5
            z_top = (wet_floors[-1] - 1) * FLOOR_HEIGHT + 0.5
            pipes.append(
                Pipe(
                    pipe_id=str(uuid.uuid4()),
                    pipe_type="riser",
                    points=[(riser_x, riser_y, z_bottom), (riser_x, riser_y, z_top)],
                    diameter_mm=110,
                    from_room_id="riser_bottom",
                    to_room_id="riser_top",
                )
            )

        return pipes

    def _build_obstacles(self) -> set:
        obstacles = set()
        for room in self.rooms:
            # Room corners are obstacles (wall centres)
            for xoff in [0, room.width]:
                for yoff in [0, room.depth]:
                    gz = (room.floor - 1) * 3.0
                    obstacles.add(world_to_grid(room.x + xoff, room.y + yoff, gz))
        return obstacles
