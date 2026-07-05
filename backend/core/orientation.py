"""
Layer 2 — orientation actuator (auto-rotate).

The room solver is sun-blind. This applies a HARD 90° rotation on top of its
output, choosing the quarter-turn that maximises insolation.score() (living room
weighted highest, so living-to-the-sun outranks bedrooms-to-the-east), subject to
plot fit. The building rotates; the plot's north (`facing`) stays fixed.

Key shortcut: scoring a building rotated by `t` quarter-turns equals scoring the
unrotated building with `facing` shifted by t·90°. So the search mutates nothing —
only the chosen winner is physically rotated.
"""

from __future__ import annotations

from core.insolation import _OCTANTS, FACING_DEG, score
from models import RoomLayout


def shift_facing(facing: str, turns: int) -> str:
    # A clockwise quarter-turn of the geometry moves each wall's compass bearing
    # by -90° (the "N"/max-y wall becomes the "W"/min-x wall), so scoring a
    # rotated building equals scoring the original with facing shifted by -90·t.
    deg = (FACING_DEG.get(facing, 0) - 90 * (turns % 4)) % 360
    return _OCTANTS[deg // 45]


def best_turns(rooms, facing, plot_w=None, plot_d=None, margin=0.5) -> int:
    """Quarter-turns (0..3, CW) that best face the rooms to the sun. Prefers
    fewer turns: a rotation is adopted only if it beats the best so far by
    `margin` — so we never rotate gratuitously (keeps the entrance where it was)."""
    minx = min(r.x for r in rooms)
    miny = min(r.y for r in rooms)
    w = max(r.x + r.width for r in rooms) - minx
    h = max(r.y + r.depth for r in rooms) - miny
    best_t, best_s = 0, score(rooms, facing)
    for t in (1, 2, 3):
        bw, bh = (h, w) if t % 2 else (w, h)  # odd turns swap the footprint
        if (plot_w and bw > plot_w + 0.01) or (plot_d and bh > plot_d + 0.01):
            continue
        s = score(rooms, shift_facing(facing, t))
        if s > best_s + margin:
            best_t, best_s = t, s
    return best_t


def _rotate_once(rooms: list[RoomLayout]) -> None:
    """Rotate every room 90° clockwise about the shared bbox (x-right, y-down),
    renormalised to the origin, carrying its doors and windows along (wall label
    + position transform) so a rotated window keeps facing the same real direction
    the rotation gives it."""
    minx = min(r.x for r in rooms)
    miny = min(r.y for r in rooms)
    h = max((r.y - miny) + r.depth for r in rooms)
    eps = 0.05
    for r in rooms:
        ox, oy, ow, od = r.x - minx, r.y - miny, r.width, r.depth
        nx, ny, nw, nd = h - (oy + od), ox, od, ow
        # Wall convention (matches the renderer's Y-flip): "S" is the min-y edge,
        # "N" the max-y edge; "W" min-x, "E" max-x. Position is offset from min-x
        # (N/S walls) or min-y (E/W walls).
        for op in (*r.doors, *r.windows):
            L = op.width
            if op.wall == "S":
                a, b = (ox + op.position, oy), (ox + op.position + L, oy)
            elif op.wall == "N":
                a, b = (ox + op.position, oy + od), (ox + op.position + L, oy + od)
            elif op.wall == "W":
                a, b = (ox, oy + op.position), (ox, oy + op.position + L)
            else:  # "E"
                a, b = (ox + ow, oy + op.position), (ox + ow, oy + op.position + L)
            # clockwise about the bbox: (X, Y) -> (h - Y, X)
            ra, rb = (h - a[1], a[0]), (h - b[1], b[0])
            if abs(ra[1] - ny) < eps and abs(rb[1] - ny) < eps:
                wall, pos = "S", min(ra[0], rb[0]) - nx
            elif abs(ra[1] - (ny + nd)) < eps and abs(rb[1] - (ny + nd)) < eps:
                wall, pos = "N", min(ra[0], rb[0]) - nx
            elif abs(ra[0] - nx) < eps and abs(rb[0] - nx) < eps:
                wall, pos = "W", min(ra[1], rb[1]) - ny
            else:
                wall, pos = "E", min(ra[1], rb[1]) - ny
            op.wall = wall
            op.position = round(max(0.0, pos), 3)
        r.x, r.y, r.width, r.depth = round(nx, 3), round(ny, 3), round(nw, 3), round(nd, 3)


def rotate_layout(rooms: list[RoomLayout], turns: int) -> None:
    """Rotate the layout in place by `turns` quarter-turns, carrying openings."""
    for _ in range(turns % 4):
        _rotate_once(rooms)
