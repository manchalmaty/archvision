from core.pdf_generator import _room_label
from models import RoomLayout, RoomType


def _room(room_type: RoomType, name: str) -> RoomLayout:
    return RoomLayout(
        room_id="r1",
        room_type=room_type,
        name=name,
        x=0,
        y=0,
        floor=1,
        width=3,
        depth=3,
        area_m2=9,
    )


def test_generated_name_is_localized():
    # The layout engine stores the English-title default when no custom name given.
    r = _room(RoomType.BEDROOM, "Bedroom")
    assert _room_label(r, "ru") == "Спальня"
    assert _room_label(r, "kk") == "Жатын бөлме"
    assert _room_label(r, "en") == "Bedroom"


def test_multiword_generated_name_is_localized():
    r = _room(RoomType.LIVING_ROOM, "Living Room")
    assert _room_label(r, "ru") == "Гостиная"


def test_custom_name_is_kept_verbatim():
    r = _room(RoomType.BEDROOM, "Кабинет")
    assert _room_label(r, "ru") == "Кабинет"
    assert _room_label(r, "en") == "Кабинет"


def test_english_label_matches_ui_even_when_default_differs():
    # backend default is "Utility"; the UI label is "Utility Room" — PDF follows UI.
    r = _room(RoomType.UTILITY, "Utility")
    assert _room_label(r, "en") == "Utility Room"


def test_unknown_lang_falls_back_to_english():
    r = _room(RoomType.KITCHEN, "Kitchen")
    assert _room_label(r, "fr") == "Kitchen"
