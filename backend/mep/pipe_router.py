"""
3D A* pipe routing for MEP (plumbing).
Routes pipes from wet zones to a central riser shaft.
"""
import heapq
import math
import uuid
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from models import RoomLayout, RoomType, GeoClimateData

WET_ZONES = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET}
GRID_STEP = 0.5  # metres per grid cell


@dataclass
class Pipe:
    pipe_id: str
    pipe_type: str  # "supply" | "drain" | "vent"
    points: List[Tuple[float, float, float]]
    diameter_mm: int
    from_room_id: str
    to_room_id: str


@dataclass(order=True)
class Node:
    f: float
    g: float = field(compare=False)
    pos: Tuple[int, int, int] = field(compare=False)
    parent: Optional["Node"] = field(compare=False, default=None)


def heuristic(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)


def astar_3d(
    start: Tuple[int, int, int],
    goal: Tuple[int, int, int],
    obstacles: set,
) -> List[Tuple[int, int, int]]:
    open_heap: list = []
    h = heuristic(start, goal)
    start_node = Node(f=h, g=0, pos=start)
    heapq.heappush(open_heap, start_node)
    came_from: dict = {start: None}
    g_score: dict = {start: 0}

    DIRS = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]

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
            nb = (current.pos[0]+dx, current.pos[1]+dy, current.pos[2]+dz)
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


def world_to_grid(x: float, y: float, z: float) -> Tuple[int, int, int]:
    return (round(x / GRID_STEP), round(y / GRID_STEP), round(z / GRID_STEP))


def grid_to_world(gx: int, gy: int, gz: int) -> Tuple[float, float, float]:
    return (gx * GRID_STEP, gy * GRID_STEP, gz * GRID_STEP)


class PipeRouter:
    def __init__(self, rooms: List[RoomLayout], floors: int, geo: Optional[GeoClimateData]):
        self.rooms = rooms
        self.floors = floors
        self.geo = geo

    def route(self) -> List[Pipe]:
        wet_rooms = [r for r in self.rooms if r.room_type in WET_ZONES]
        if not wet_rooms:
            return []

        # Riser shaft at centroid of wet zones on floor 1
        riser_x = sum(r.x + r.width / 2 for r in wet_rooms) / len(wet_rooms)
        riser_y = sum(r.y + r.depth / 2 for r in wet_rooms) / len(wet_rooms)

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

            pipes.append(Pipe(
                pipe_id=str(uuid.uuid4()),
                pipe_type="drain",
                points=[grid_to_world(*p) for p in path_drain],
                diameter_mm=110,
                from_room_id=room.room_id,
                to_room_id="riser",
            ))

            # Supply: pressurised cold water, runs near ceiling (2.2m above slab)
            rz_supply = floor_base + 2.2
            start_supply = world_to_grid(rx, ry, rz_supply)
            goal_supply = world_to_grid(riser_x, riser_y, rz_supply)
            path_supply = astar_3d(start_supply, goal_supply, obstacles)
            if not path_supply:
                path_supply = [start_supply, goal_supply]

            pipes.append(Pipe(
                pipe_id=str(uuid.uuid4()),
                pipe_type="supply",
                points=[grid_to_world(*p) for p in path_supply],
                diameter_mm=25,
                from_room_id="supply_main",
                to_room_id=room.room_id,
            ))

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
