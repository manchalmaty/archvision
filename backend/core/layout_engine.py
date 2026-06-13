"""
2D floor plan layout engine.
Packs rooms using a greedy strip algorithm, groups wet zones together.
"""

import math
import uuid

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
        """Place doors and windows on every room based on adjacency."""
        WALLS = ("S", "N", "W", "E")

        for room in layouts:
            same_floor = [r for r in layouts if r.floor == room.floor]

            # Classify each wall as internal (adjacent to another room) or external
            adj: dict[str, list] = {w: _adjacent_rooms(room, w, same_floor) for w in WALLS}
            internal = [w for w in WALLS if adj[w]]
            external = [w for w in WALLS if not adj[w]]

            # ── Doors ────────────────────────────────────────────────────────
            dw, dh = DOOR_SPECS.get(room.room_type, DEFAULT_DOOR)

            if room.room_type == RoomType.HALLWAY:
                # The hallway gets exactly ONE entrance door, on an external wall.
                # Interior connections are owned by each neighbouring room (the
                # branch below), so emitting a door per internal wall here would
                # double up doors on every shared boundary.
                entrance = external[0] if external else (internal[0] if internal else None)
                if entrance:
                    wlen = _wall_len(room, entrance)
                    room.doors.append(
                        DoorSpec(
                            wall=entrance, position=_place_opening(wlen, dw), width=dw, height=dh
                        )
                    )
            else:
                hallway_walls = [
                    w for w in internal if any(r.room_type == RoomType.HALLWAY for r in adj[w])
                ]
                door_wall = (hallway_walls or internal or external or [None])[0]
                if door_wall:
                    wlen = _wall_len(room, door_wall)
                    room.doors.append(
                        DoorSpec(
                            wall=door_wall, position=_place_opening(wlen, dw), width=dw, height=dh
                        )
                    )

            # ── Windows — ГОСТ 23166 ─────────────────────────────────────────
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
        """Auto-inject hallway and toilet if user omitted them."""
        types = {r.room_type for r in rooms}
        if RoomType.HALLWAY not in types:
            rooms.append(RoomInput(room_type=RoomType.HALLWAY, area_m2=5.0, name="Hallway"))
        if RoomType.TOILET not in types:
            rooms.append(RoomInput(room_type=RoomType.TOILET, area_m2=2.0, name="Toilet"))
        return rooms

    def _distribute_floors(self, rooms: list):
        floors = self.params.floors

        # Ground-floor priority: plumbing zones + entry
        ground = [r for r in rooms if r.room_type in GROUND_FLOOR_ZONES]
        upper = [r for r in rooms if r.room_type not in GROUND_FLOOR_ZONES]

        per_floor: list[list] = [[] for _ in range(floors)]
        per_floor[0].extend(ground)

        # Distribute upper-floor rooms by area balance
        upper_sorted = sorted(upper, key=lambda r: r.area_m2, reverse=True)
        floor_totals = [sum(r.area_m2 for r in f) for f in per_floor]
        for room in upper_sorted:
            min_floor = floor_totals.index(min(floor_totals))
            per_floor[min_floor].append(room)
            floor_totals[min_floor] += room.area_m2

        return per_floor

    def _layout_floor(self, floor: int, rooms) -> list[RoomLayout]:
        shape = getattr(self.params, "building_shape", "rectangular")
        if shape == "l_shape":
            return self._layout_l(floor, rooms)
        elif shape == "u_shape":
            return self._layout_u(floor, rooms)
        elif shape == "t_shape":
            return self._layout_t(floor, rooms)
        elif shape == "square":
            return self._layout_tiled(floor, rooms, aspect_factor=1.0)
        return self._layout_tiled(floor, rooms, aspect_factor=1.35)

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

    def _layout_strip(
        self,
        floor: int,
        rooms,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        target_w: float | None = None,
        aspect_factor: float = 1.2,
    ) -> list[RoomLayout]:
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
        # Respect the plot for EVERY strip (main body and L/U/T wings alike):
        # a strip starting at offset_x may only use the remaining plot width.
        if self.params.plot_width_m:
            available = self.params.plot_width_m - offset_x
            if available > 1.0:
                target_w = min(target_w, available)

        # Pass 1: bin rooms into rows
        raw_rows: list[list[tuple]] = []
        current_row: list[tuple] = []
        current_width = 0.0
        for room in ordered:
            w, d = room_dims(room.room_type, room.area_m2)
            if current_row and current_width + w > target_w:
                raw_rows.append(current_row)
                current_row = [(room, w, d)]
                current_width = w
            else:
                current_row.append((room, w, d))
                current_width += w
        if current_row:
            raw_rows.append(current_row)

        # Pass 2: bounded proportional scale — compute max/min RF before applying
        layouts = []
        cursor_y = offset_y
        for row in raw_rows:
            row_sum_w = sum(w for _, w, _ in row)
            ideal_scale = target_w / row_sum_w if row_sum_w > 0.01 else 1.0
            row_max_rf = float("inf")
            row_min_rf = 0.0
            for room, w, d in row:
                max_asp = ROOM_MAX_ASPECT.get(room.room_type, MAX_ASPECT)
                cur_asp = (w / d) if d > 0 else 1.0
                row_max_rf = min(row_max_rf, math.sqrt(max_asp / cur_asp))
                row_min_rf = max(row_min_rf, math.sqrt(cur_asp / max_asp))
            rf = max(row_min_rf, min(ideal_scale, row_max_rf))
            scaled = []
            for room, w, _d in row:
                fw = max(round(w * rf, 3), 0.5)
                fd = round(room.area_m2 / fw, 3)
                scaled.append((room, fw, fd))
            row_depth = round(max(fd for _, _, fd in scaled), 3)
            cursor_x = offset_x
            for room, fw, _fd in scaled:
                layouts.append(
                    RoomLayout(
                        room_id=str(uuid.uuid4()),
                        room_type=room.room_type,
                        name=room.name or room.room_type.value.replace("_", " ").title(),
                        x=round(cursor_x, 3),
                        y=round(cursor_y, 3),
                        floor=floor,
                        width=fw,
                        depth=row_depth,
                        area_m2=room.area_m2,
                    )
                )
                cursor_x += fw
            cursor_y += row_depth
        return layouts

    def _layout_l(self, floor: int, rooms) -> list[RoomLayout]:
        """Г-образный: service core (main body) + private wing extending down-right."""
        MAIN_TYPES = {
            RoomType.HALLWAY,
            RoomType.BATHROOM,
            RoomType.TOILET,
            RoomType.KITCHEN,
            RoomType.LIVING_ROOM,
        }
        main_r = [r for r in rooms if r.room_type in MAIN_TYPES]
        wing_r = [r for r in rooms if r.room_type not in MAIN_TYPES]
        if not wing_r or not main_r:
            return self._layout_strip(floor, rooms, aspect_factor=1.2)
        main = self._layout_strip(floor, main_r, offset_x=0.0, offset_y=0.0)
        main_max_x = max(r.x + r.width for r in main)
        main_max_y = max(r.y + r.depth for r in main)
        wing_area = sum(r.area_m2 for r in wing_r)
        wing_tw = round(math.sqrt(wing_area * 1.2), 2)
        wing_ox = round(main_max_x * 0.45, 3)
        wing = self._layout_strip(
            floor, wing_r, offset_x=wing_ox, offset_y=main_max_y, target_w=wing_tw
        )
        return main + wing

    def _layout_u(self, floor: int, rooms) -> list[RoomLayout]:
        """П-образный: left wing + center + right wing (U footprint)."""

        def _ok(r):
            try:
                return (ROOM_ORDER.index(r.room_type), -r.area_m2)
            except ValueError:
                return (len(ROOM_ORDER), -r.area_m2)

        ordered = sorted(rooms, key=_ok)
        n = len(ordered)
        left_n = max(1, n // 3)
        right_n = max(1, n // 3)
        center_n = max(1, n - left_n - right_n)
        left_r = ordered[:left_n]
        center_r = ordered[left_n : left_n + center_n]
        right_r = ordered[left_n + center_n :]
        if not center_r or not right_r:
            return self._layout_strip(floor, rooms, aspect_factor=1.2)
        wing_tw = round(math.sqrt(sum(r.area_m2 for r in left_r) * 0.7), 2)
        left = self._layout_strip(floor, left_r, offset_x=0.0, offset_y=0.0, target_w=wing_tw)
        left_max_x = max(r.x + r.width for r in left)
        center_tw = round(math.sqrt(sum(r.area_m2 for r in center_r) * 1.2), 2)
        center = self._layout_strip(
            floor, center_r, offset_x=left_max_x, offset_y=0.0, target_w=center_tw
        )
        center_max_x = max(r.x + r.width for r in center) if center else left_max_x
        right_tw = round(math.sqrt(sum(r.area_m2 for r in right_r) * 0.7), 2)
        right = self._layout_strip(
            floor, right_r, offset_x=center_max_x, offset_y=0.0, target_w=right_tw
        )
        return left + center + right

    def _layout_t(self, floor: int, rooms) -> list[RoomLayout]:
        """Т-образный: wide top bar + narrow stem centered below."""

        def _ok(r):
            try:
                return (ROOM_ORDER.index(r.room_type), -r.area_m2)
            except ValueError:
                return (len(ROOM_ORDER), -r.area_m2)

        ordered = sorted(rooms, key=_ok)
        n = len(ordered)
        top_n = max(1, int(n * 0.65))
        top_r = ordered[:top_n]
        stem_r = ordered[top_n:]
        if not stem_r:
            return self._layout_strip(floor, rooms, aspect_factor=1.2)
        top = self._layout_strip(floor, top_r, offset_x=0.0, offset_y=0.0)
        top_max_x = max(r.x + r.width for r in top)
        top_max_y = max(r.y + r.depth for r in top)
        stem_tw = round(top_max_x * 0.4, 2)
        stem_ox = round((top_max_x - stem_tw) / 2, 3)
        stem = self._layout_strip(
            floor, stem_r, offset_x=stem_ox, offset_y=top_max_y, target_w=stem_tw
        )
        return top + stem
