import itertools

from core.orientation import best_turns, rotate_layout, shift_facing
from models import RoomLayout, RoomType, WindowSpec
from tests.conftest import rooms_overlap


def _room(rt: RoomType, x, y, w, d, *walls: str) -> RoomLayout:
    return RoomLayout(
        room_id=f"{rt.value}-{x}-{y}",
        room_type=rt,
        name="x",
        x=x,
        y=y,
        floor=1,
        width=w,
        depth=d,
        area_m2=w * d,
        windows=[
            WindowSpec(wall=wl, position=0.5, width=1.2, height=1.0, sill=0.9) for wl in walls
        ],
    )


def test_shift_facing():
    assert shift_facing("N", 1) == "W"  # clockwise geometry turn → -90° bearing
    assert shift_facing("N", 2) == "S"
    assert shift_facing("E", 2) == "W"
    assert shift_facing("NE", 1) == "NW"
    assert shift_facing("N", 4) == "N"


def test_rotate_preserves_area_and_tiles():
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3), _room(RoomType.KITCHEN, 4, 0, 2, 3)]
    a0 = sum(r.width * r.depth for r in rooms)
    rotate_layout(rooms, 1)
    assert abs(sum(r.width * r.depth for r in rooms) - a0) < 1e-6
    for a, b in itertools.combinations(rooms, 2):
        assert not rooms_overlap(a, b)
    w = max(r.x + r.width for r in rooms)
    h = max(r.y + r.depth for r in rooms)
    assert abs(w - 3) < 0.01 and abs(h - 6) < 0.01  # 6x3 → 3x6


def test_four_turns_is_identity():
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3), _room(RoomType.KITCHEN, 4, 0, 2, 3)]
    orig = [(r.x, r.y, r.width, r.depth) for r in rooms]
    rotate_layout(rooms, 4)
    for (x, y, w, d), r in zip(orig, rooms, strict=True):
        assert abs(r.x - x) < 0.01 and abs(r.y - y) < 0.01
        assert abs(r.width - w) < 0.01 and abs(r.depth - d) < 0.01


def test_rotation_carries_openings():
    # A window on the north wall faces east after one clockwise turn,
    # and returns to north (same wall + position) after four.
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3, "N")]
    rooms[0].windows[0].position = 1.0
    rotate_layout(rooms, 1)
    assert rooms[0].windows[0].wall == "W"  # max-y "N" wall → min-x "W" wall (CW)
    rotate_layout(rooms, 3)  # total 4 → identity
    w = rooms[0].windows[0]
    assert w.wall == "N" and abs(w.position - 1.0) < 0.02


def test_best_turns_faces_living_to_the_sun():
    # Living window on plan "N": facing N → north (poor). 180° → south (good).
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3, "N")]
    assert best_turns(rooms, "N") == 2


def test_best_turns_respects_plot_fit():
    # 6x3 building on a 6.5x3.5 plot → odd turns (3x6) overflow depth, excluded.
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3, "E"), _room(RoomType.KITCHEN, 4, 0, 2, 3, "E")]
    assert best_turns(rooms, "N", plot_w=6.5, plot_d=3.5) in (0, 2)


def test_no_gratuitous_rotation_when_already_good():
    # Living already faces south → no rotation beats it by the margin.
    rooms = [_room(RoomType.LIVING_ROOM, 0, 0, 4, 3, "S")]
    assert best_turns(rooms, "N") == 0
