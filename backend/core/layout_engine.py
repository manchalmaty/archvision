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

WET_ZONES = {RoomType.KITCHEN, RoomType.BATHROOM, RoomType.TOILET}

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
    RoomType.GARAGE: 2.4,
}


OPEN_TOL = 0.08  # adjacency tolerance (m)
MIN_CORNER = 0.3  # min clearance from wall corner to opening edge (m)

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
                DoorSpec(wall=wall, position=_door_pos(child, parent, wall, dw), width=dw, height=dh)
            )

        root = next((r for r in rooms if r.room_type == RoomType.HALLWAY), rooms[0])

        # Entrance door for the root, on an external wall.
        radj = {w: _adjacent_rooms(root, w, rooms) for w in WALLS}
        rext = [w for w in WALLS if not radj[w]]
        rint = [w for w in WALLS if radj[w]]
        entrance = (rext or rint or [None])[0]
        if entrance:
            dw, dh = DOOR_SPECS.get(root.room_type, DEFAULT_DOOR)
            root.doors.append(
                DoorSpec(
                    wall=entrance, position=_place_opening(_wall_len(root, entrance), dw),
                    width=dw, height=dh,
                )
            )

        # BFS tree from the root. Pass 1 expands only through dry rooms so wet
        # rooms become leaves; a door is placed on each child facing its parent.
        visited = {root.room_id}
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
                    if nb.room_type not in WET_ZONES:
                        queue.append(nb)

        # Pass 2: rooms only reachable through a wet room — connect to any visited
        # neighbour as a last resort so nothing is stranded.
        for r in rooms:
            if r.room_id in visited:
                continue
            for w in WALLS:
                parent = next((n for n in _adjacent_rooms(r, w, rooms) if n.room_id in visited), None)
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
                room.windows.append(
                    WindowSpec(
                        wall=w, position=_place_opening(wlen, ww), width=ww, height=wh, sill=sill
                    )
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
        ground_pref = GROUND_FLOOR_ZONES | {RoomType.LIVING_ROOM}
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
    _SHAPE_ASPECT = {"square": 1.0, "rectangular": 1.35, "l_shape": 1.3, "u_shape": 1.4, "t_shape": 1.45}

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

    def _emit_row(self, layouts, floor, group, ox, oy, width) -> float:
        """Lay one row of rooms spanning [ox, ox+width] exactly; return next y."""
        if not group:
            return oy

        def _order_key(r):
            try:
                return ROOM_ORDER.index(r.room_type)
            except ValueError:
                return len(ROOM_ORDER)

        group = sorted(group, key=_order_key)
        area = sum(r.area_m2 for r in group)
        rh = round(area / width, 3) if width > 0 else 0.0
        x = ox
        for i, room in enumerate(group):
            rw = round(ox + width - x, 3) if i == len(group) - 1 else round(room.area_m2 / rh, 3)
            layouts.append(
                RoomLayout(
                    room_id=str(uuid.uuid4()),
                    room_type=room.room_type,
                    name=room.name or room.room_type.value.replace("_", " ").title(),
                    x=round(x, 3),
                    y=round(oy, 3),
                    floor=floor,
                    width=rw,
                    depth=rh,
                    area_m2=room.area_m2,
                )
            )
            x += rw
        return round(oy + rh, 3)

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
        hall = halls[0] if halls else None

        total_area = sum(r.area_m2 for r in rooms)
        width = round(math.sqrt(total_area * aspect_factor), 2)
        if self.params.plot_width_m:
            width = min(width, self.params.plot_width_m)
        width = max(width, 3.0)

        # Split rooms into two bands; keep wet zones together when possible.
        wet = [r for r in others if r.room_type in WET_ZONES]
        dry = [r for r in others if r.room_type not in WET_ZONES]
        if wet and dry:
            north, south = dry, wet
        else:
            pool = sorted(others, key=lambda r: -r.area_m2)
            north, south, an, asth = [], [], 0.0, 0.0
            for r in pool:
                if an <= asth:
                    north.append(r)
                    an += r.area_m2
                else:
                    south.append(r)
                    asth += r.area_m2

        # Size the footprint so each band is both deep enough for its deepest
        # room AND wide enough that its narrowest room clears its minimum side.
        # Upper bound (depth): width <= band_area / deepest_min.
        # Lower bound (width): width >= narrowest_min * band_area / room_area.
        # When the two conflict (too many rooms for one row) the width bound wins
        # and the invariant checker honestly reports the remaining shortfall.
        for band in (north, south):
            if not band:
                continue
            band_area = sum(r.area_m2 for r in band)
            deepest = max(USABLE_MIN_SIDE.get(r.room_type, 1.5) for r in band)
            width = min(width, band_area / deepest)
            for r in band:
                need_w = USABLE_MIN_SIDE.get(r.room_type, 1.5)
                width = max(width, need_w * band_area / r.area_m2)
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
            return gh >= 1.0 and all((r.area_m2 / gh) >= 0.7 for r in group)

        if not (_row_ok(north) and _row_ok(south)):
            return self._layout_tiled(floor, rooms, aspect_factor=aspect_factor)

        layouts: list[RoomLayout] = []
        y = self._emit_row(layouts, floor, north, 0.0, 0.0, width)
        if hall is not None:
            hall_h = round(max(hall.area_m2 / width, 1.3), 3)
            layouts.append(
                RoomLayout(
                    room_id=str(uuid.uuid4()),
                    room_type=hall.room_type,
                    name=hall.name or "Hallway",
                    x=0.0,
                    y=round(y, 3),
                    floor=floor,
                    width=width,
                    depth=hall_h,
                    area_m2=hall.area_m2,
                )
            )
            y = round(y + hall_h, 3)
        self._emit_row(layouts, floor, south, 0.0, y, width)
        return layouts
