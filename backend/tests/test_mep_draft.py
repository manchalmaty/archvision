from mep.clash_detector import ClashDetector
from models import RoomLayout, RoomType


def _r(rt: RoomType, x, y, w, d, floor=1, name="r") -> RoomLayout:
    return RoomLayout(
        room_id=f"{rt.value}-{x}-{y}-{floor}",
        room_type=rt,
        name=name,
        x=x,
        y=y,
        floor=floor,
        width=w,
        depth=d,
        area_m2=w * d,
    )


def _types(rooms) -> set[str]:
    return {c.conflict_type for c in ClashDetector(rooms, []).detect()}


def test_far_from_riser_flagged():
    # Riser sits in the big bathroom at the origin; the kitchen is ~12 m away.
    rooms = [
        _r(RoomType.BATHROOM, 0, 0, 4, 4, name="Bath"),
        _r(RoomType.KITCHEN, 12, 0, 3, 3, name="Kitchen"),
    ]
    assert "far_from_riser" in _types(rooms)


def test_grouped_wet_zone_not_flagged():
    rooms = [_r(RoomType.BATHROOM, 0, 0, 3, 3), _r(RoomType.TOILET, 3, 0, 2, 3)]
    assert "far_from_riser" not in _types(rooms)


def test_laundry_is_a_wet_point():
    # Utility (laundry) far from the riser is flagged like any other wet room.
    rooms = [
        _r(RoomType.BATHROOM, 0, 0, 4, 4, name="Bath"),
        _r(RoomType.UTILITY, 12, 0, 3, 3, name="Laundry"),
    ]
    assert "far_from_riser" in _types(rooms)


def test_wet_over_living_flagged():
    rooms = [
        _r(RoomType.LIVING_ROOM, 0, 0, 4, 4, floor=1, name="Living"),
        _r(RoomType.BATHROOM, 0, 0, 3, 3, floor=2, name="Bath"),
    ]
    assert "wet_over_dry" in _types(rooms)


def test_wet_over_wet_is_ok():
    rooms = [
        _r(RoomType.BATHROOM, 0, 0, 3, 3, floor=1),
        _r(RoomType.BATHROOM, 0, 0, 3, 3, floor=2),
    ]
    assert "wet_over_dry" not in _types(rooms)
