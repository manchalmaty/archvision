"""PDF door symbols must match the 2D viewer: a swing arc for hinged doors
only — a cased opening or a garage gate rendered with a 2-3 m arc reads as a
door that cannot physically exist."""

from reportlab.graphics.shapes import PolyLine

from core.pdf_generator import _floor_plan_drawing
from models import DoorSpec, RoomLayout, RoomType


def _room(rid, rt, x, w, doors):
    return RoomLayout(
        room_id=rid,
        room_type=rt,
        name=rt.value.replace("_", " ").title(),
        x=x,
        y=0,
        floor=1,
        width=w,
        depth=4,
        area_m2=w * 4,
        doors=doors,
    )


def _arcs(drawing):
    return [e for e in drawing.contents if isinstance(e, PolyLine)]


def test_swing_door_draws_one_arc():
    rooms = [
        _room("a", RoomType.BEDROOM, 0, 4, [DoorSpec(wall="E", position=1.5, width=0.8)]),
        _room("b", RoomType.LIVING_ROOM, 4, 4, []),
    ]
    assert len(_arcs(_floor_plan_drawing(rooms, 400, "f1"))) == 1


def test_opening_draws_no_arc():
    rooms = [
        _room(
            "a",
            RoomType.KITCHEN,
            0,
            4,
            [DoorSpec(wall="E", position=1.0, width=2.0, kind="opening")],
        ),
        _room(
            "b",
            RoomType.LIVING_ROOM,
            4,
            4,
            [DoorSpec(wall="W", position=1.0, width=2.0, kind="opening")],
        ),
    ]
    assert _arcs(_floor_plan_drawing(rooms, 400, "f1")) == []


def test_gate_draws_no_arc():
    rooms = [
        _room("g", RoomType.GARAGE, 0, 6, [DoorSpec(wall="N", position=0.3, width=2.4, kind="gate")])
    ]
    assert _arcs(_floor_plan_drawing(rooms, 400, "f1")) == []
