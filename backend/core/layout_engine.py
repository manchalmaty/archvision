"""
2D floor plan layout engine.
Packs rooms using a greedy strip algorithm, groups wet zones together.
"""

import math
import uuid
from collections import deque

from models import (
    BuildingParams,
    DoorSpec,
    GeoClimateData,
    RoomInput,
    RoomLayout,
    RoomType,
    WindowSpec,
)

# UTILITY included: a laundry/хозблок is plumbing (mep.pipe_router agrees) and
# belongs on the wet band's riser wall. Banded with the bedrooms it became a
# 0.65 m sliver in the deep dry band — the family preset's tiled-fallback bug.
WET_ZONES = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET, RoomType.UTILITY}

# Private rooms are never a through-route: the door tree must not adopt another
# room as a child *of* a bedroom, or you would walk through the bedroom to reach
# it (invariant rule 4). So bedrooms stay leaves, like wet rooms.
PRIVATE_ZONES = {RoomType.BEDROOM}

# Rooms that must be on ground floor (plumbing access)
GROUND_FLOOR_ZONES = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET, RoomType.HALLWAY}

# Architectural ordering: entry → wet service → social → private → utility
ROOM_ORDER = [
    RoomType.HALLWAY,
    RoomType.BATHROOM,
    RoomType.TOILET,
    RoomType.KITCHEN,
    RoomType.LIVING_ROOM,
    RoomType.BEDROOM,
    RoomType.UTILITY,
    RoomType.GARAGE,
]

MAX_ASPECT = 1.6  # default max w:d or d:w ratio for living spaces

# Per-type max aspect — hallways/garages/toilets are naturally elongated; living spaces must be near-square
ROOM_MAX_ASPECT: dict[RoomType, float] = {
    RoomType.BEDROOM: 1.5,
    RoomType.LIVING_ROOM: 1.5,
    RoomType.KITCHEN: 1.6,
    RoomType.BATHROOM: 1.4,
    RoomType.TOILET: 2.0,
    RoomType.HALLWAY: 4.0,
    RoomType.UTILITY: 2.0,
    RoomType.GARAGE: 3.0,
}

# Target aspect ratio per room type (width:depth) — closer to square = better ergonomics
ROOM_ASPECT: dict[RoomType, float] = {
    RoomType.BEDROOM: 1.15,
    RoomType.LIVING_ROOM: 1.25,
    RoomType.KITCHEN: 1.2,
    RoomType.BATHROOM: 1.0,
    RoomType.TOILET: 0.75,
    RoomType.HALLWAY: 2.5,
    RoomType.UTILITY: 1.2,
    RoomType.GARAGE: 2.0,
}

# Minimum dimensions per room type (m)
MIN_DIMS: dict[RoomType, tuple[float, float]] = {
    RoomType.BATHROOM: (1.5, 1.5),
    RoomType.TOILET: (0.9, 1.2),
    RoomType.HALLWAY: (1.2, 2.0),
}

# Narrowest usable side per room type (m): a room must clear this in BOTH
# dimensions or furniture will not fit. Shared by the layout engine (to size
# bands) and the invariant checker (rule 9), so they cannot drift apart.
USABLE_MIN_SIDE: dict[RoomType, float] = {
    RoomType.LIVING_ROOM: 2.4,
    RoomType.BEDROOM: 2.4,
    RoomType.KITCHEN: 1.8,
    RoomType.BATHROOM: 1.5,
    RoomType.TOILET: 0.8,
    RoomType.HALLWAY: 0.9,
    RoomType.UTILITY: 1.2,
    # A car is ~1.8–2.0 m wide and the gate is 2.4 m: a 2.4 m garage cannot be
    # entered. 3.0 is the physical floor, not a comfort preference.
    RoomType.GARAGE: 3.0,
}


OPEN_TOL = 0.08  # adjacency tolerance (m)
MIN_CORNER = 0.3  # min clearance from wall corner to opening edge (m)

# Budget ↔ spacious slider (params.spaciousness, 0..1). One intuitive control:
# room areas scale within ±20%, so the budget end yields smaller rooms AND a
# smaller footprint (less perimeter → less exterior wall, insulation and heat
# loss → cheaper), the spacious end larger and pricier. 0.5 is neutral.
SPACIOUSNESS_AREA_MIN = 0.80
SPACIOUSNESS_AREA_MAX = 1.20


def area_factor(spaciousness: float) -> float:
    s = min(max(spaciousness, 0.0), 1.0)
    return SPACIOUSNESS_AREA_MIN + (SPACIOUSNESS_AREA_MAX - SPACIOUSNESS_AREA_MIN) * s


def scale_room_areas(rooms: list, spaciousness: float) -> list:
    """Return room copies with areas scaled by the spaciousness factor."""
    factor = area_factor(spaciousness)
    if abs(factor - 1.0) < 1e-9:
        return rooms
    return [
        r.model_copy(update={"area_m2": min(round(r.area_m2 * factor, 2), 200.0)}) for r in rooms
    ]


# Number of windows per room type (0 = none)
WINDOW_COUNTS: dict[RoomType, int] = {
    RoomType.LIVING_ROOM: 2,
    RoomType.BEDROOM: 1,
    RoomType.KITCHEN: 1,
    RoomType.BATHROOM: 1,
    RoomType.TOILET: 0,
    RoomType.HALLWAY: 0,
    RoomType.UTILITY: 1,
    RoomType.GARAGE: 1,
}

# Window specs (width, height, sill) in metres — GOST 23166
WIN_SPECS: dict[RoomType, tuple[float, float, float]] = {
    RoomType.LIVING_ROOM: (1.5, 1.5, 0.85),  # 1500×1500, широкое
    RoomType.BEDROOM: (1.3, 1.4, 0.85),  # 1300×1400, стандарт
    RoomType.KITCHEN: (1.2, 1.4, 0.85),  # 1200×1400, кухонное
    RoomType.BATHROOM: (0.6, 0.9, 0.80),  # 600×900, маленькое
    RoomType.TOILET: (0.6, 0.9, 0.80),  # 600×900
    RoomType.UTILITY: (0.7, 1.1, 0.85),  # 700×1100, среднее
    RoomType.GARAGE: (1.0, 1.0, 1.00),  # гараж
}

# Door specs (width, height) in metres — ГОСТ / СП 54
DOOR_SPECS: dict[RoomType, tuple[float, float]] = {
    RoomType.HALLWAY: (0.9, 2.05),  # входная дверь
    RoomType.BATHROOM: (0.7, 2.0),  # дверь в ванную
    RoomType.TOILET: (0.7, 2.0),  # дверь в туалет
    RoomType.GARAGE: (2.4, 2.1),  # ворота гаража
}
DEFAULT_DOOR = (0.8, 2.0)  # межкомнатная

# A "single volume" social zone (open/mixed planning): the wall between the
# kitchen and the living room becomes a wide cased opening (no leaf) instead of a
# door. Width is clamped to this range so it reads as an opening, not a doorway.
SOCIAL_ROOMS = {RoomType.LIVING_ROOM, RoomType.KITCHEN}
SOCIAL_OPENING_MIN = 1.6
SOCIAL_OPENING_MAX = 3.0


def _wall_len(room: RoomLayout, wall: str) -> float:
    return room.width if wall in ("N", "S") else room.depth


def _adjacent_rooms(room: RoomLayout, wall: str, all_rooms: list) -> list:
    """Return rooms that share the given wall of `room` on the same floor."""
    result = []
    for other in all_rooms:
        if other.room_id == room.room_id:
            continue
        if wall == "S":
            if abs(other.y + other.depth - room.y) < OPEN_TOL:
                if (
                    other.x < room.x + room.width - OPEN_TOL
                    and other.x + other.width > room.x + OPEN_TOL
                ):
                    result.append(other)
        elif wall == "N":
            if abs(other.y - (room.y + room.depth)) < OPEN_TOL:
                if (
                    other.x < room.x + room.width - OPEN_TOL
                    and other.x + other.width > room.x + OPEN_TOL
                ):
                    result.append(other)
        elif wall == "W":
            if abs(other.x + other.width - room.x) < OPEN_TOL:
                if (
                    other.y < room.y + room.depth - OPEN_TOL
                    and other.y + other.depth > room.y + OPEN_TOL
                ):
                    result.append(other)
        elif wall == "E":
            if abs(other.x - (room.x + room.width)) < OPEN_TOL:
                if (
                    other.y < room.y + room.depth - OPEN_TOL
                    and other.y + other.depth > room.y + OPEN_TOL
                ):
                    result.append(other)
    return result


def _shared_len(a: RoomLayout, b: RoomLayout) -> float:
    """Length of the wall segment two rooms share (0 if they don't touch)."""
    if abs(a.x + a.width - b.x) < OPEN_TOL or abs(b.x + b.width - a.x) < OPEN_TOL:
        return max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    if abs(a.y + a.depth - b.y) < OPEN_TOL or abs(b.y + b.depth - a.y) < OPEN_TOL:
        return max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    return 0.0


def _door_pos(room: RoomLayout, neighbor: RoomLayout, wall: str, dw: float) -> float:
    """Door offset that centres the leaf on the segment shared with `neighbor`,
    so the opening always lands in the real doorway (not on a blank wall)."""
    if wall in ("N", "S"):
        lo, hi = max(room.x, neighbor.x), min(room.x + room.width, neighbor.x + neighbor.width)
        center = (lo + hi) / 2 - room.x
    else:
        lo, hi = max(room.y, neighbor.y), min(room.y + room.depth, neighbor.y + neighbor.depth)
        center = (lo + hi) / 2 - room.y
    wlen = _wall_len(room, wall)
    return round(min(max(center - dw / 2, 0.0), max(0.0, wlen - dw)), 3)


def _place_opening(wall_len: float, opening_width: float) -> float:
    """Center opening in wall, respecting MIN_CORNER clearance.

    On walls too short for corner clearances the opening is centered without
    them; the position never lets the opening overflow the wall, so renderers
    can trust the data as-is.
    """
    usable = wall_len - 2 * MIN_CORNER
    if usable < opening_width:
        return round(max(0.0, (wall_len - opening_width) / 2), 3)
    return round(MIN_CORNER + (usable - opening_width) / 2, 3)


def room_dims(room_type: RoomType, area: float) -> tuple[float, float]:
    aspect = ROOM_ASPECT.get(room_type, 1.3)
    width = math.sqrt(area * aspect)
    depth = area / width
    if room_type in MIN_DIMS:
        min_w, min_d = MIN_DIMS[room_type]
        width = max(width, min_w)
        depth = max(depth, min_d)
    # Clamp initial aspect ratio so scaling starts from a reasonable base
    max_asp = ROOM_MAX_ASPECT.get(room_type, MAX_ASPECT)
    if depth > 0 and width / depth > max_asp:
        width = math.sqrt(area * max_asp)
        depth = area / width
    elif depth > 0 and depth / width > max_asp:
        depth = math.sqrt(area * max_asp)
        width = area / depth
    return round(width, 2), round(depth, 2)


class LayoutEngine:
    def __init__(self, params: BuildingParams, geo: GeoClimateData):
        self.params = params
        self.geo = geo
        # Non-blocking issues found during layout (e.g. plot overflow);
        # the API route merges these into GenerationResult.warnings.
        self.warnings: list[str] = []

    def generate(self) -> list[RoomLayout]:
        rooms = self._ensure_essentials(list(self.params.rooms))
        rooms = scale_room_areas(rooms, getattr(self.params, "spaciousness", 0.5))
        rooms_per_floor = self._distribute_floors(rooms)
        layouts = []
        for floor_idx, floor_rooms in enumerate(rooms_per_floor):
            floor_layouts = self._layout_floor(floor_idx + 1, floor_rooms)
            layouts.extend(floor_layouts)
        self._assign_openings(layouts)
        self._check_plot_fit(layouts)
        return layouts

    def _check_plot_fit(self, layouts: list[RoomLayout]) -> None:
        """Warn when the packed footprint exceeds the plot dimensions."""
        pw, pd = self.params.plot_width_m, self.params.plot_depth_m
        if not layouts or (not pw and not pd):
            return
        bw = max(r.x + r.width for r in layouts)
        bd = max(r.y + r.depth for r in layouts)
        if pw and bw > pw + 0.01:
            self.warnings.append(
                f"Building width {bw:.1f} m exceeds plot width {pw:.1f} m. "
                f"Reduce room areas, or add floors to shrink the footprint."
            )
        if pd and bd > pd + 0.01:
            self.warnings.append(
                f"Building depth {bd:.1f} m exceeds plot depth {pd:.1f} m. "
                f"Reduce room areas, or add floors to shrink the footprint."
            )

    def _assign_openings(self, layouts: list[RoomLayout]) -> None:
        """Place doors and windows on every room.

        Doors form a connected tree rooted at the hallway: every room gets one
        door to its parent (the neighbour closer to the entrance), so the whole
        plan is reachable. Wet rooms (bath/toilet) are kept as leaves — the tree
        never routes *through* them — so you never walk through a toilet to reach
        a living space.
        """
        for floor in {r.floor for r in layouts}:
            self._assign_floor_doors([r for r in layouts if r.floor == floor])
        self._assign_windows(layouts)

    def _assign_floor_doors(self, rooms: list[RoomLayout]) -> None:
        WALLS = ("S", "N", "W", "E")
        if not rooms:
            return

        def wall_facing(a: RoomLayout, b: RoomLayout) -> str | None:
            return next((w for w in WALLS if b in _adjacent_rooms(a, w, rooms)), None)

        def add_door(child: RoomLayout, parent: RoomLayout, wall: str) -> None:
            dw, dh = DOOR_SPECS.get(child.room_type, DEFAULT_DOOR)
            child.doors.append(
                DoorSpec(
                    wall=wall, position=_door_pos(child, parent, wall, dw), width=dw, height=dh
                )
            )

        # Closed/mixed root at the hallway; open plan has none, so the living
        # room (the social entry) roots the tree.
        root = (
            next((r for r in rooms if r.room_type == RoomType.HALLWAY), None)
            or next((r for r in rooms if r.room_type == RoomType.LIVING_ROOM), None)
            or rooms[0]
        )

        # Entrance door for the root, on an external wall.
        radj = {w: _adjacent_rooms(root, w, rooms) for w in WALLS}
        rext = [w for w in WALLS if not radj[w]]
        rint = [w for w in WALLS if radj[w]]
        entrance = (rext or rint or [None])[0]
        if entrance:
            dw, dh = DOOR_SPECS.get(root.room_type, DEFAULT_DOOR)
            root.doors.append(
                DoorSpec(
                    wall=entrance,
                    position=_place_opening(_wall_len(root, entrance), dw),
                    width=dw,
                    height=dh,
                )
            )

        # Garage doors are planned, not grown: the vehicle gate belongs on an
        # external wall (it is not the pedestrian entrance — rule 6 exempts it)
        # and the person-door picks a mudroom-order neighbour. Left to pass 2,
        # the garage hangs its 2.4 m gate into whatever room got visited first.
        visited = {root.room_id}
        for g in rooms:
            if g.room_type is RoomType.GARAGE and g.room_id not in visited:
                self._assign_garage_doors(g, rooms)
                visited.add(g.room_id)

        # BFS tree from the root. Pass 1 expands only through dry rooms so wet
        # rooms become leaves; a door is placed on each child facing its parent.
        queue = deque([root])
        while queue:
            cur = queue.popleft()
            for w in WALLS:
                for nb in _adjacent_rooms(cur, w, rooms):
                    if nb.room_id in visited or _shared_len(nb, cur) < DEFAULT_DOOR[0]:
                        continue
                    cw = wall_facing(nb, cur)
                    if cw is None:
                        continue
                    add_door(nb, cur, cw)
                    visited.add(nb.room_id)
                    if nb.room_type not in WET_ZONES and nb.room_type not in PRIVATE_ZONES:
                        queue.append(nb)

        # Pass 2: rooms only reachable through a wet room — connect to any visited
        # neighbour as a last resort so nothing is stranded.
        for r in rooms:
            if r.room_id in visited:
                continue
            for w in WALLS:
                parent = next(
                    (n for n in _adjacent_rooms(r, w, rooms) if n.room_id in visited), None
                )
                if parent:
                    add_door(r, parent, w)
                    visited.add(r.room_id)
                    break

        # Pass 3: an isolated room with no adjacency at all — give it any door.
        for r in rooms:
            if r.doors:
                continue
            adjr = {w: _adjacent_rooms(r, w, rooms) for w in WALLS}
            w = ([x for x in WALLS if adjr[x]] or list(WALLS))[0]
            dw, dh = DOOR_SPECS.get(r.room_type, DEFAULT_DOOR)
            r.doors.append(
                DoorSpec(wall=w, position=_place_opening(_wall_len(r, w), dw), width=dw, height=dh)
            )

        # Open/mixed planning: dissolve the kitchen↔living wall into one wide
        # cased opening so they read as a single volume.
        if getattr(self.params, "openness", "closed") != "closed":
            self._open_social_zone(rooms)

    # Mudroom order for the garage person-door; a bedroom parent would trip
    # rule 4 and a wet closet is a plumbing stack, not a mudroom.
    _GARAGE_DOOR_PREF = (
        RoomType.UTILITY,
        RoomType.KITCHEN,
        RoomType.HALLWAY,
        RoomType.LIVING_ROOM,
    )

    def _assign_garage_doors(self, garage: RoomLayout, rooms: list[RoomLayout]) -> None:
        WALLS = ("S", "N", "W", "E")
        adj = {w: _adjacent_rooms(garage, w, rooms) for w in WALLS}
        gw, gh = DOOR_SPECS[RoomType.GARAGE]
        gate_wall = next((w for w in WALLS if not adj[w] and _wall_len(garage, w) >= gw), None)
        if gate_wall:
            wlen = _wall_len(garage, gate_wall)
            # Corner-aligned, not centred: a vehicle bay hugs one side and the
            # rest of the wall stays free for a window.
            garage.doors.append(
                DoorSpec(
                    wall=gate_wall,
                    position=round(min(MIN_CORNER, max(0.0, wlen - gw)), 3),
                    width=gw,
                    height=gh,
                    kind="gate",
                )
            )

        dw, dh = DEFAULT_DOOR
        candidates = [(w, n) for w in WALLS for n in adj[w] if _shared_len(garage, n) >= dw]
        if not candidates:
            return  # pass 3 still guarantees a door if the gate had no wall either

        def rank(item):
            n = item[1]
            if n.room_type in self._GARAGE_DOOR_PREF:
                return self._GARAGE_DOOR_PREF.index(n.room_type)
            if n.room_type in PRIVATE_ZONES:
                return 99
            if n.room_type in (RoomType.BATHROOM, RoomType.TOILET):
                return 98
            return 50

        w, n = min(candidates, key=rank)
        garage.doors.append(
            DoorSpec(wall=w, position=_door_pos(garage, n, w, dw), width=dw, height=dh)
        )

    def _open_social_zone(self, rooms: list[RoomLayout]) -> None:
        openness = getattr(self.params, "openness", "closed")
        k = next((r for r in rooms if r.room_type == RoomType.KITCHEN), None)
        lv = next((r for r in rooms if r.room_type == RoomType.LIVING_ROOM), None)
        hall = next((r for r in rooms if r.room_type == RoomType.HALLWAY), None)
        # Kitchen + living read as one volume in both open and mixed.
        self._open_pair(rooms, k, lv)
        # In "open", the entry hallway is opened up to the social volume too —
        # an entry buffer with no walled corridor.
        if openness == "open":
            self._open_pair(rooms, hall, lv or k)

    @staticmethod
    def _open_pair(rooms: list[RoomLayout], a: RoomLayout | None, b: RoomLayout | None) -> None:
        """Replace the wall between two adjacent rooms with one wide cased opening."""
        if not a or not b:
            return
        WALLS = ("S", "N", "W", "E")
        OPP = {"S": "N", "N": "S", "W": "E", "E": "W"}
        wall = next((w for w in WALLS if b in _adjacent_rooms(a, w, rooms)), None)
        shared = _shared_len(a, b)
        if wall is None or shared < SOCIAL_OPENING_MIN:
            return  # not adjacent (degenerate banding) — leave them separate
        ow = round(min(max(shared - 2 * MIN_CORNER, SOCIAL_OPENING_MIN), SOCIAL_OPENING_MAX), 2)
        # The opening sits on BOTH rooms' shared wall (the two coincide on screen),
        # so each room owns an opening — neither is left "doorless" (rule 3).
        a.doors = [d for d in a.doors if d.wall != wall]
        b.doors = [d for d in b.doors if d.wall != OPP[wall]]
        a.doors.append(
            DoorSpec(
                wall=wall, position=_door_pos(a, b, wall, ow), width=ow, height=2.1, kind="opening"
            )
        )
        b.doors.append(
            DoorSpec(
                wall=OPP[wall],
                position=_door_pos(b, a, OPP[wall], ow),
                width=ow,
                height=2.1,
                kind="opening",
            )
        )

    def _assign_windows(self, layouts: list[RoomLayout]) -> None:
        WALLS = ("S", "N", "W", "E")
        for room in layouts:
            same_floor = [r for r in layouts if r.floor == room.floor]
            external = [w for w in WALLS if not _adjacent_rooms(room, w, same_floor)]
            needed = WINDOW_COUNTS.get(room.room_type, 1)
            ww, wh, sill = WIN_SPECS.get(room.room_type, (1.3, 1.4, 0.85))
            placed = 0
            for w in external:
                if placed >= needed:
                    break
                wlen = _wall_len(room, w)
                if wlen < ww + 2 * MIN_CORNER:
                    continue
                pos = _place_opening(wlen, ww)
                # An external door (entrance, garage gate) may already claim
                # this stretch of wall — a window inside a doorway is nonsense.
                if any(
                    d.wall == w and pos < d.position + d.width and d.position < pos + ww
                    for d in room.doors
                ):
                    continue
                room.windows.append(
                    WindowSpec(wall=w, position=pos, width=ww, height=wh, sill=sill)
                )
                placed += 1

    def _ensure_essentials(self, rooms: list) -> list:
        """Auto-inject the rooms a dwelling cannot legally lack: hallway, a
        toilet, and a kitchen (a home without a kitchen is uninhabitable — see
        invariant rule 8)."""
        types = {r.room_type for r in rooms}
        if RoomType.HALLWAY not in types:
            rooms.append(RoomInput(room_type=RoomType.HALLWAY, area_m2=5.0, name="Hallway"))
        if RoomType.TOILET not in types:
            rooms.append(RoomInput(room_type=RoomType.TOILET, area_m2=2.0, name="Toilet"))
        if RoomType.KITCHEN not in types:
            rooms.append(RoomInput(room_type=RoomType.KITCHEN, area_m2=8.0, name="Kitchen"))
        return rooms

    def _distribute_floors(self, rooms: list):
        floors = self.params.floors

        # Ground floor holds the service core and the social room (wet zones +
        # hallway + living room). Private rooms (bedrooms, etc.) go upstairs when
        # there is an upstairs — this is the normal arrangement and it also keeps
        # the ground floor from cramming a lone bedroom in beside the wet band.
        # Cars do not climb stairs: the garage is pinned to the ground floor
        # alongside the plumbing core.
        ground_pref = GROUND_FLOOR_ZONES | {RoomType.LIVING_ROOM, RoomType.GARAGE}
        ground = [r for r in rooms if r.room_type in ground_pref]
        private = [r for r in rooms if r.room_type not in ground_pref]

        per_floor: list[list] = [[] for _ in range(floors)]
        per_floor[0].extend(ground)

        if floors == 1:
            per_floor[0].extend(private)
            return per_floor

        # Balance private rooms across the UPPER floors only.
        upper = list(range(1, floors))
        totals = dict.fromkeys(upper, 0.0)
        for room in sorted(private, key=lambda r: r.area_m2, reverse=True):
            f = min(upper, key=lambda i: totals[i])
            per_floor[f].append(room)
            totals[f] += room.area_m2

        return per_floor

    # Footprint proportions per shape. Every shape now uses the central-hall
    # layout: the wing layouts (L/U/T) stranded the hallway in a corner touching
    # only wet rooms, which forced circulation through a toilet. A compact
    # central corridor is a usable plan for every silhouette; the shape only
    # nudges how wide vs deep the footprint is.
    _SHAPE_ASPECT = {
        "square": 1.0,
        "rectangular": 1.35,
        "l_shape": 1.3,
        "u_shape": 1.4,
        "t_shape": 1.45,
    }

    def _layout_floor(self, floor: int, rooms) -> list[RoomLayout]:
        shape = getattr(self.params, "building_shape", "rectangular")
        aspect = self._SHAPE_ASPECT.get(shape, 1.35)
        return self._layout_central_hall(floor, rooms, aspect_factor=aspect)

    def _layout_tiled(
        self,
        floor: int,
        rooms,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        target_w: float | None = None,
        aspect_factor: float = 1.35,
    ) -> list[RoomLayout]:
        """Slice-and-dice tiling: gap-free and overlap-free by construction.

        Rooms are binned into rows by a target width; each row's height is then
        set so the row spans the target width *exactly* (Σ widths = target_w),
        and rows stack to fill a target_w × (total_area/target_w) rectangle with
        no ragged edges. Aspect ratios stay reasonable because binning uses each
        room's natural width, but tiling is never sacrificed for them.
        """
        if not rooms:
            return []

        def _order_key(r):
            try:
                return (ROOM_ORDER.index(r.room_type), -r.area_m2)
            except ValueError:
                return (len(ROOM_ORDER), -r.area_m2)

        ordered = sorted(rooms, key=_order_key)
        total_area = sum(r.area_m2 for r in ordered)
        if target_w is None:
            target_w = round(math.sqrt(total_area * aspect_factor), 2)
        if self.params.plot_width_m:
            available = self.params.plot_width_m - offset_x
            if available > 1.0:
                target_w = min(target_w, available)
        target_w = max(target_w, 1.5)

        # Bin rooms into rows using their natural width, breaking a row once it
        # would overflow target_w (keeps per-row aspect ratios sane).
        rows: list[list] = []
        current: list = []
        cur_w = 0.0
        for room in ordered:
            w, _d = room_dims(room.room_type, room.area_m2)
            if current and cur_w + w > target_w * 1.05:
                rows.append(current)
                current = [room]
                cur_w = w
            else:
                current.append(room)
                cur_w += w
        if current:
            rows.append(current)

        layouts: list[RoomLayout] = []
        cursor_y = offset_y
        for row in rows:
            row_area = sum(r.area_m2 for r in row)
            # Row height chosen so the row's rooms span target_w exactly.
            row_h = round(row_area / target_w, 3)
            cursor_x = offset_x
            for i, room in enumerate(row):
                # Last room in the row absorbs rounding slack to hit target_w cleanly.
                if i == len(row) - 1:
                    rw = round(offset_x + target_w - cursor_x, 3)
                else:
                    rw = round(room.area_m2 / row_h, 3) if row_h > 0 else target_w
                layouts.append(
                    RoomLayout(
                        room_id=str(uuid.uuid4()),
                        room_type=room.room_type,
                        name=room.name or room.room_type.value.replace("_", " ").title(),
                        x=round(cursor_x, 3),
                        y=round(cursor_y, 3),
                        floor=floor,
                        width=rw,
                        depth=row_h,
                        area_m2=room.area_m2,
                    )
                )
                cursor_x += rw
            cursor_y += row_h
        return layouts

    # Small wet closets that may share one stacked column when their band is
    # too deep for their areas — bathroom+toilet in one column is the classic
    # "санузел столбиком" and keeps them on one plumbing wall (rule 5 bonus).
    _STACKABLE = (RoomType.BATHROOM, RoomType.TOILET, RoomType.UTILITY)

    @staticmethod
    def _donated_widths(cells, width, rh=None) -> list[float]:
        """Span for each cell of a row (cell = [room] or a stacked column).

        Spans start area-proportional; a donation pass then lets cells with
        spare span top up cells below their usable minimum (a donor never
        drops below its own minimum nor 90% of its area — rule 2's floor), so
        a 1.5 m² toilet can sit in a deep band beside bedrooms without the
        whole house being widened to save it. Symmetric: called with
        (members-as-cells, rh, cell_width) it distributes DEPTHS inside a
        stacked column. `rh` is the perpendicular extent (defaults to the
        exact-tiling depth area/width; a garage band passes its floored one).
        """
        area = sum(r.area_m2 for cell in cells for r in cell)
        if rh is None:
            rh = area / width if width > 0 else 0.0
        if rh <= 0 or width <= 0:
            return [0.0] * len(cells)
        shares = [sum(r.area_m2 for r in cell) for cell in cells]
        widths = [width * s / area for s in shares]
        needs = [max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in cell) for cell in cells]
        donor_floor = [max(n, 0.901 * s / rh) for n, s in zip(needs, shares)]
        deficit = sum(max(0.0, n - w) for n, w in zip(needs, widths))
        surplus = sum(max(0.0, w - f) for f, w in zip(donor_floor, widths))
        if 0 < deficit <= surplus:
            scale = deficit / surplus
            widths = [
                n if w < n else w - max(0.0, w - f) * scale
                for w, n, f in zip(widths, needs, donor_floor)
            ]
        return widths

    @classmethod
    def _cells_clear(cls, cells, width, rh=None) -> bool:
        """Post-donation, does every cell (and every stacked member) clear its
        usable minimum in BOTH directions?"""
        ws = cls._donated_widths(cells, width, rh)
        for w, cell in zip(ws, cells):
            if w < max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in cell) - 1e-9:
                return False
            if len(cell) > 1:
                if rh is None:
                    total = sum(r.area_m2 for c in cells for r in c)
                    rh = total / width if width > 0 else 0.0
                depths = cls._donated_widths([[m] for m in cell], rh, w)
                for d, m in zip(depths, cell):
                    if d < USABLE_MIN_SIDE.get(m.room_type, 1.5) - 1e-9:
                        return False
        return True

    @classmethod
    def _stack_cells(cls, group, width):
        """Cells for one band, stacking small wet rooms into one column when
        plain proportional widths (plus donation) cannot clear the minimums.

        Returns None when stacking is unnecessary or impossible — the caller
        keeps the legacy one-room-per-cell row, so passing programs keep their
        exact geometry. The column members sort largest-first; the emitter
        turns that into "biggest wet room faces the hallway" so the toilet
        tucks behind the bathroom, not the other way around.
        """
        area = sum(r.area_m2 for r in group)
        depth = area / width if width > 0 else 0.0
        if depth <= 0:
            return None
        singles = [[r] for r in group]
        if cls._cells_clear(singles, width):
            return None
        wet = [r for r in group if r.room_type in cls._STACKABLE]
        if len(wet) < 2:
            return None
        # Every member's minimum must fit along the column's depth.
        if sum(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in wet) > depth + 1e-9:
            return None
        cells = [[r] for r in group if r.room_type not in cls._STACKABLE]
        cells.append(sorted(wet, key=lambda r: -r.area_m2))
        return cells

    def _emit_row(
        self, layouts, floor, group, ox, oy, width, hall_side="end", min_depth=0.0
    ) -> float:
        """Lay one row of cells spanning [ox, ox+width] exactly; return next y.

        A cell is one room or a stacked wet column (see _stack_cells). The
        stack's largest member faces the hallway (`hall_side` = which y-edge of
        this row touches it), so the toilet sits behind the bathroom. A row
        with `min_depth` (garage: a car physically needs 3.0 m) may emit deeper
        than area/width — its rooms honestly GROW rather than turn unusable.
        """
        if not group:
            return oy

        def _order_key(r):
            try:
                return ROOM_ORDER.index(r.room_type)
            except ValueError:
                return len(ROOM_ORDER)

        def emit(room, x, y, w, d):
            layouts.append(
                RoomLayout(
                    room_id=str(uuid.uuid4()),
                    room_type=room.room_type,
                    name=room.name or room.room_type.value.replace("_", " ").title(),
                    x=round(x, 3),
                    y=round(y, 3),
                    floor=floor,
                    width=w,
                    depth=d,
                    area_m2=room.area_m2,
                )
            )

        group = sorted(group, key=_order_key)
        area = sum(r.area_m2 for r in group)
        rh = round(max(area / width, min_depth), 3) if width > 0 else 0.0
        cells = self._stack_cells(group, width) or [[r] for r in group]
        cells.sort(key=lambda c: _order_key(c[0]))
        widths = self._donated_widths(cells, width, rh)
        x = ox
        for i, cell in enumerate(cells):
            cw = round(ox + width - x, 3) if i == len(cells) - 1 else round(widths[i], 3)
            if len(cell) == 1:
                emit(cell[0], x, oy, cw, rh)
            else:
                members = cell if hall_side == "start" else list(reversed(cell))
                depths = self._donated_widths([[m] for m in members], rh, cw)
                y = oy
                for j, m in enumerate(members):
                    md = round(oy + rh - y, 3) if j == len(members) - 1 else round(depths[j], 3)
                    emit(m, x, y, cw, md)
                    y = round(y + md, 3)
            x += cw
        return round(oy + rh, 3)

    @staticmethod
    def _balance_bands(others):
        """Greedy split into two area-balanced bands (no wet/social grouping)."""
        north, south, an, asth = [], [], 0.0, 0.0
        for r in sorted(others, key=lambda r: -r.area_m2):
            if an <= asth:
                north.append(r)
                an += r.area_m2
            else:
                south.append(r)
                asth += r.area_m2
        return north, south

    def _layout_central_hall(self, floor: int, rooms, aspect_factor: float = 1.3):
        """Central-corridor plan: a full-width hallway band splits the rooms into
        two rows, one above and one below, so EVERY room opens directly off the
        hallway (a real distribution node, not a linear enfilade). Wet zones are
        grouped into one band to share a plumbing wall. Falls back to slice-and-
        dice tiling when a single-row band would force unusably narrow rooms.
        """
        halls = [r for r in rooms if r.room_type == RoomType.HALLWAY]
        others = [r for r in rooms if r.room_type != RoomType.HALLWAY]
        if not others:
            return self._layout_tiled(floor, rooms, aspect_factor=aspect_factor)
        # Upper floors carry no hallway — they still get the two-band, min-size
        # treatment, just without a central corridor strip between the bands.
        openness = getattr(self.params, "openness", "closed")
        # Every mode keeps the hallway as an entry buffer; "open" merely opens it
        # up to the social volume (see _open_social_zone) rather than removing it.
        hall = halls[0] if halls else None

        total_area = sum(r.area_m2 for r in rooms)
        width = round(math.sqrt(total_area * aspect_factor), 2)
        if self.params.plot_width_m:
            width = min(width, self.params.plot_width_m)
        width = max(width, 3.0)

        # A garage is a footprint outlier: inside a shared band its area inflates
        # the min-side width raise below until the OTHER band's depth collapses
        # (the documented "kitchen ~1.3 m" shortfall). It gets its own full-width
        # band at the back instead — max-y = compass north in this engine, so it
        # doubles as a cold-side thermal buffer and steals no habitable daylight.
        buffer_band = [r for r in others if r.room_type == RoomType.GARAGE]
        banded = [r for r in others if r.room_type != RoomType.GARAGE]
        if not banded:  # garage-only program — nothing to protect from it
            buffer_band, banded = [], others

        # Split rooms into two bands.
        #   closed → dry north / wet south (kitchen shares the wet plumbing wall).
        #   open|mixed → social zone (living+kitchen) north / everything else
        #     south, so the kitchen sits beside the living room and the two can
        #     open into a single volume.
        if openness in ("open", "mixed"):
            social = [r for r in banded if r.room_type in SOCIAL_ROOMS]
            service = [r for r in banded if r.room_type not in SOCIAL_ROOMS]
            north, south = (
                (social, service) if (social and service) else self._balance_bands(banded)
            )
        else:
            wet = [r for r in banded if r.room_type in WET_ZONES]
            dry = [r for r in banded if r.room_type not in WET_ZONES]
            north, south = (dry, wet) if (wet and dry) else self._balance_bands(banded)

        # Size the footprint so each band is both deep enough for its deepest
        # room AND wide enough that its narrowest cell clears its minimum side.
        # Upper bound (depth): width <= band_area / deepest_min.
        # Lower bound (width): width >= narrowest_min * band_area / cell_area.
        # A band whose narrow rooms can be rescued in-row (donation from
        # neighbours with spare width, or stacking small wet rooms into one
        # column) does NOT raise the width. When a raise is still needed it is
        # CLAMPED to the habitable bands' depth caps: saving a 1.2 m² toilet
        # must never flatten every other band to 1.5–2 m — that unbounded raise
        # is exactly what used to ship whole unusable houses. Any remaining
        # shortfall stays visible: check_invariants flags it red in the route.
        for band in (north, south, buffer_band):
            if not band:
                continue
            band_area = sum(r.area_m2 for r in band)
            deepest = max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in band)
            width = min(width, band_area / deepest)
        ceiling = min(
            (
                sum(r.area_m2 for r in band)
                / max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in band)
                for band in (north, south)
                if band
            ),
            default=width,
        )
        for band in (north, south, buffer_band):
            if not band:
                continue
            cells = self._stack_cells(band, width) or [[r] for r in band]
            if self._cells_clear(cells, width):
                continue
            band_area = sum(r.area_m2 for r in band)
            for cell in cells:
                need_w = max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in cell)
                cell_area = sum(r.area_m2 for r in cell)
                width = max(width, min(need_w * band_area / cell_area, ceiling))
        if self.params.plot_width_m:
            width = min(width, self.params.plot_width_m)
        width = max(width, 2.0)

        # Guard: only reject central-hall for genuinely degenerate bands (a room
        # thinner than 0.7 m). For everything else central-hall beats an enfilade,
        # so we prefer it even when proportions are merely tight.
        def _row_ok(group) -> bool:
            if not group:
                return True
            gh = sum(r.area_m2 for r in group) / width
            # Judge the cells _emit_row will actually produce (stacking +
            # donation), or a row those mechanisms rescue gets rejected first.
            cells = self._stack_cells(group, width) or [[r] for r in group]
            return gh >= 1.0 and all(w >= 0.7 for w in self._donated_widths(cells, width))

        if not (_row_ok(north) and _row_ok(south) and _row_ok(buffer_band)):
            return self._layout_tiled(floor, rooms, aspect_factor=aspect_factor)

        # The hallway band has a 1.3 m depth floor, so on a wide house it
        # balloons past its request (the "15.6 m² прихожая" report — 20% of the
        # house as corridor, whose printed dimension is the whole building
        # width). When it overshoots 1.6×, the strip's W end goes to the
        # smallest toilet/utility that fits a 1.3 m band (a guest WC by the
        # entrance is classic planning) — the hall then prints its REAL extent.
        # W end because the south band's wet cells sort first (ROOM_ORDER), so
        # the pulled toilet lands on the bathroom's riser wall; the emit is
        # re-verified and falls back to the legacy full band if the wet
        # cluster would split (rule 5) anyway.
        hall_h = round(max(hall.area_m2 / width, 1.3), 3) if hall is not None else 0.0
        filler = None
        if hall is not None and width * hall_h > 1.6 * hall.area_m2:
            candidates = sorted(
                (
                    r
                    for r in (*north, *south)
                    if r.room_type in (RoomType.TOILET, RoomType.UTILITY)
                    and USABLE_MIN_SIDE.get(r.room_type, 1.5) <= hall_h + 1e-9
                ),
                key=lambda r: r.area_m2,
            )
            for cand in candidates:
                wt = round(max(cand.area_m2 / hall_h, USABLE_MIN_SIDE[cand.room_type]), 3)
                band = north if cand in north else south
                if wt > 0.35 * width or len(band) <= 1:
                    continue
                # The donor band was SIZED with this room's area: pulling it
                # must not sink the band's depth below its deepest min (that
                # starved the kitchen to 1.5 m) nor break its cell minimums —
                # the hallway gain is cosmetic, never worth a new red flag.
                rest = [r for r in band if r is not cand]
                rest_area = sum(r.area_m2 for r in rest)
                deepest_rest = max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in rest)
                if rest_area / width < deepest_rest - 1e-9:
                    continue
                rest_cells = self._stack_cells(rest, width) or [[r] for r in rest]
                if not self._cells_clear(rest_cells, width):
                    continue
                filler = (cand, wt)
                break

        def _emit_floor(pulled) -> list[RoomLayout]:
            rows: list[RoomLayout] = []
            nb = [r for r in north if pulled is None or r is not pulled[0]]
            sb = [r for r in south if pulled is None or r is not pulled[0]]
            y = self._emit_row(rows, floor, nb, 0.0, 0.0, width, hall_side="end")
            if hall is not None:
                hx = 0.0
                if pulled is not None:
                    cand, wt = pulled
                    rows.append(
                        RoomLayout(
                            room_id=str(uuid.uuid4()),
                            room_type=cand.room_type,
                            name=cand.name or cand.room_type.value.replace("_", " ").title(),
                            x=0.0,
                            y=round(y, 3),
                            floor=floor,
                            width=wt,
                            depth=hall_h,
                            area_m2=cand.area_m2,
                        )
                    )
                    hx = wt
                rows.append(
                    RoomLayout(
                        room_id=str(uuid.uuid4()),
                        room_type=hall.room_type,
                        name=hall.name or "Hallway",
                        x=hx,
                        y=round(y, 3),
                        floor=floor,
                        width=round(width - hx, 3),
                        depth=hall_h,
                        area_m2=hall.area_m2,
                    )
                )
                y = round(y + hall_h, 3)
            y = self._emit_row(rows, floor, sb, 0.0, y, width, hall_side="start")
            # The buffer band is the garage: its depth has a physical floor (a
            # car does not shrink with the budget) — the band may grow past its
            # requested area rather than emit a garage no car can enter.
            buffer_min = (
                max(USABLE_MIN_SIDE.get(r.room_type, 0.0) for r in buffer_band)
                if buffer_band
                else 0.0
            )
            self._emit_row(
                rows, floor, buffer_band, 0.0, y, width, hall_side="start", min_depth=buffer_min
            )
            return rows

        def _wet_connected(rows: list[RoomLayout]) -> bool:
            wet_types = {RoomType.BATHROOM, RoomType.TOILET}
            if openness == "closed":
                wet_types.add(RoomType.KITCHEN)
            wet = [r for r in rows if r.room_type in wet_types]
            if len(wet) < 2:
                return True
            seen, stack = {wet[0].room_id}, [wet[0]]
            while stack:
                cur = stack.pop()
                for other in wet:
                    if other.room_id not in seen and _shared_len(cur, other) > 0.05:
                        seen.add(other.room_id)
                        stack.append(other)
            return len(seen) == len(wet)

        if filler is not None:
            layouts = _emit_floor(filler)
            if _wet_connected(layouts):
                return layouts
        return _emit_floor(None)
