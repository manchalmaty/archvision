from core.plan_validator import PlanRoom, validate_plan


def _has_narrow_error(errors: list[str]) -> bool:
    return any("furniture will not fit" in e for e in errors)


def test_pencil_living_room_is_rejected():
    # A 9x2 m living room (2 m deep) is geometrically clean but unusable — the
    # validator must reject it so the LLM loop falls back to the rule engine.
    rooms = [
        PlanRoom("lv", "living_room", "Living", 0, 0, 9, 2),
        PlanRoom("hall", "hallway", "Hall", 0, 2, 9, 1.5),
    ]
    errors, _ = validate_plan(rooms, 9, 3.5, "rectangular")
    assert _has_narrow_error(errors)


def test_usable_living_room_passes_min_side():
    rooms = [
        PlanRoom("lv", "living_room", "Living", 0, 0, 5, 4),
        PlanRoom("hall", "hallway", "Hall", 0, 4, 5, 1.5),
    ]
    errors, _ = validate_plan(rooms, 5, 5.5, "rectangular")
    assert not _has_narrow_error(errors)


def test_narrow_toilet_still_allowed():
    # A 0.8 m-wide toilet is fine — service rooms have no habitable min side.
    rooms = [
        PlanRoom("wc", "toilet", "WC", 0, 0, 0.9, 1.4),
        PlanRoom("hall", "hallway", "Hall", 0, 1.4, 0.9, 1.5),
    ]
    errors, _ = validate_plan(rooms, 0.9, 3.0, "rectangular")
    assert not _has_narrow_error(errors)
