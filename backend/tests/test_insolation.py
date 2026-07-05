from core.insolation import annotate, score
from models import RoomLayout, RoomType, WindowSpec


def _room(rt: RoomType, *window_walls: str) -> RoomLayout:
    return RoomLayout(
        room_id="r",
        room_type=rt,
        name="x",
        x=0,
        y=0,
        floor=1,
        width=4,
        depth=4,
        area_m2=16,
        windows=[
            WindowSpec(wall=w, position=0.5, width=1.2, height=1.0, sill=0.9) for w in window_walls
        ],
    )


def _sun(rt: RoomType, facing: str, *walls: str) -> str:
    r = _room(rt, *walls)
    annotate([r], facing)
    return r.sun


def test_south_living_good_north_poor():
    assert _sun(RoomType.LIVING_ROOM, "N", "S") == "good"
    assert _sun(RoomType.LIVING_ROOM, "N", "N") == "poor"


def test_bedroom_prefers_east():
    assert _sun(RoomType.BEDROOM, "N", "E") == "good"
    assert _sun(RoomType.BEDROOM, "N", "N") == "poor"


def test_wet_and_service_rooms_unrated():
    for rt in (RoomType.BATHROOM, RoomType.TOILET, RoomType.HALLWAY, RoomType.GARAGE):
        assert _sun(rt, "N", "S") == ""


def test_room_without_windows_unrated():
    assert _sun(RoomType.LIVING_ROOM, "N") == ""


def test_facing_rotates_ratings():
    # Window on the plan "N" wall: facing N → real north (poor);
    # facing S → that same wall now points real south (good).
    assert _sun(RoomType.LIVING_ROOM, "N", "N") == "poor"
    assert _sun(RoomType.LIVING_ROOM, "S", "N") == "good"


def test_score_prefers_living_to_the_sun():
    south = [_room(RoomType.LIVING_ROOM, "S"), _room(RoomType.BEDROOM, "N")]
    north = [_room(RoomType.LIVING_ROOM, "N"), _room(RoomType.BEDROOM, "E")]
    # Living room is weighted highest, so south-living wins despite the bedroom.
    assert score(south, "N") > score(north, "N")
