"""
Daylight (insolation) sensor.

Rates each habitable room by the real compass direction its windows face, given
the building's `facing` (the bearing the plan's "N" wall points to). This is a
SENSOR only — it never moves rooms. Layer 2 (auto-rotate) reuses `score()` to
pick the best of four orientations, with the living room weighted highest so
"living room to the sun" outranks "bedrooms to the east".
"""

from __future__ import annotations

from models import RoomLayout, RoomType

FACING_DEG = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
_OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
# Offset of each plan wall from the "N" wall (which points at `facing`).
_WALL_OFFSET = {"N": 0, "E": 90, "S": 180, "W": 270}

# Daylight quality per real octant, by what the room wants:
#   south-seeking (living room, kitchen) and east-seeking (bedroom, morning sun).
_SOUTH_PREF = {
    "S": 1.0,
    "SE": 0.85,
    "SW": 0.85,
    "E": 0.55,
    "W": 0.55,
    "NE": 0.4,
    "NW": 0.4,
    "N": 0.2,
}
_EAST_PREF = {"E": 1.0, "SE": 0.9, "NE": 0.8, "S": 0.7, "SW": 0.55, "W": 0.4, "NW": 0.3, "N": 0.35}

_SOUTH_ROOMS = {RoomType.LIVING_ROOM, RoomType.KITCHEN}
_EAST_ROOMS = {RoomType.BEDROOM}
_SUN_ROOMS = _SOUTH_ROOMS | _EAST_ROOMS
_LIVING = {RoomType.LIVING_ROOM}


def _octant(bearing: float) -> str:
    return _OCTANTS[round(bearing / 45) % 8]


def _wall_octant(wall: str, facing: str) -> str:
    bearing = (FACING_DEG.get(facing, 0) + _WALL_OFFSET.get(wall, 0)) % 360
    return _octant(bearing)


def _room_quality(room: RoomLayout, facing: str) -> float | None:
    """Best daylight quality (0..1) over the room's windows, type-aware.
    None = not a daylight room, or no windows to rate."""
    if room.room_type not in _SUN_ROOMS or not room.windows:
        return None
    pref = _EAST_PREF if room.room_type in _EAST_ROOMS else _SOUTH_PREF
    return max(pref[_wall_octant(w.wall, facing)] for w in room.windows)


def _rate(q: float) -> str:
    return "good" if q >= 0.7 else "ok" if q >= 0.45 else "poor"


def annotate(rooms: list[RoomLayout], facing: str) -> None:
    """Set `room.sun` for every room in place (sensor annotation)."""
    for r in rooms:
        q = _room_quality(r, facing)
        r.sun = _rate(q) if q is not None else ""


def score(rooms: list[RoomLayout], facing: str) -> float:
    """Overall daylight score 0..100. Living rooms weighted highest so the
    actuator prioritises living-to-the-sun over bedrooms-to-the-east."""
    num = den = 0.0
    for r in rooms:
        q = _room_quality(r, facing)
        if q is None:
            continue
        w = 3.0 if r.room_type in _LIVING else 1.0
        num += w * q
        den += w
    return round(100 * num / den, 1) if den else 0.0
