"""Garage-in-own-band: a big garage must not starve the wet band.

With two shared bands, the garage inflates its band's area, the min-side raise
pushes the shared width up, and the wet band's depth collapses below the
kitchen's usable minimum (the documented "kitchen ~1.3 m" shortfall).
"""

from core.geo_calculator import GeoClimateCalculator
from core.layout_engine import USABLE_MIN_SIDE, LayoutEngine, _adjacent_rooms
from core.plan_invariants import check_invariants
from models import BuildingParams, CountryCode, RoomInput, RoomType

GEO = GeoClimateCalculator().calculate(CountryCode.RU, None, 1)

GARAGE_HEAVY = [
    RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=16),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.BEDROOM, area_m2=12),
    RoomInput(room_type=RoomType.KITCHEN, area_m2=9),
    RoomInput(room_type=RoomType.BATHROOM, area_m2=4),
    RoomInput(room_type=RoomType.TOILET, area_m2=1.5),
    RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
    RoomInput(room_type=RoomType.GARAGE, area_m2=24),
]


def _gen(room_inputs):
    params = BuildingParams(rooms=room_inputs, country=CountryCode.RU, floors=1)
    return LayoutEngine(params, GEO).generate()


def test_garage_heavy_all_rooms_clear_min_sides():
    rooms = _gen(GARAGE_HEAVY)
    for r in rooms:
        need = USABLE_MIN_SIDE.get(r.room_type, 0.0)
        assert (
            min(r.width, r.depth) >= need - 1e-6
        ), f"{r.room_type.value}: {r.width:.2f}×{r.depth:.2f} < min {need}"


def test_garage_heavy_passes_all_invariants():
    rooms = _gen(GARAGE_HEAVY)
    violations = check_invariants(rooms)
    assert violations == [], [f"{v.rule}: {v.message}" for v in violations]


def test_garage_gets_its_own_full_width_band():
    rooms = _gen(GARAGE_HEAVY)
    garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
    plan_w = max(r.x + r.width for r in rooms) - min(r.x for r in rooms)
    assert abs(garage.width - plan_w) < 0.02, "garage should span the full plan width"
    # Thermal buffer at the back (max-y = compass north in this engine).
    assert garage.y + garage.depth >= max(r.y + r.depth for r in rooms) - 1e-6


def test_garage_still_reachable_and_doored():
    rooms = _gen(GARAGE_HEAVY)
    garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
    assert garage.doors, "garage must keep a door (invariant rule 3)"


def test_program_without_garage_unchanged_band_count():
    no_garage = [r for r in GARAGE_HEAVY if r.room_type != RoomType.GARAGE]
    rooms = _gen(no_garage)
    violations = check_invariants(rooms)
    assert violations == [], [f"{v.rule}: {v.message}" for v in violations]


def _garage_and_floor(rooms):
    garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
    return garage, [r for r in rooms if r.floor == garage.floor]


def _door_target(room, door, floor_rooms):
    """Room whose extent overlaps the door leaf the most (None = exterior)."""
    lo = (room.x if door.wall in ("N", "S") else room.y) + door.position
    hi = lo + door.width
    best, best_len = None, 0.0
    for n in _adjacent_rooms(room, door.wall, floor_rooms):
        nlo, nhi = (n.x, n.x + n.width) if door.wall in ("N", "S") else (n.y, n.y + n.depth)
        overlap = min(hi, nhi) - max(lo, nlo)
        if overlap > best_len:
            best, best_len = n, overlap
    return best


def test_garage_vehicle_gate_on_external_wall():
    garage, fr = _garage_and_floor(_gen(GARAGE_HEAVY))
    gates = [d for d in garage.doors if d.width >= 2.0]
    assert gates, "garage lost its vehicle gate"
    for gate in gates:
        assert gate.kind == "gate", "vehicle gate must not render as a swing door"
        assert not _adjacent_rooms(
            garage, gate.wall, fr
        ), f"vehicle gate on wall {gate.wall} must open to the street, not into the house"


def test_garage_person_door_into_sensible_room():
    garage, fr = _garage_and_floor(_gen(GARAGE_HEAVY))
    inner = [d for d in garage.doors if _adjacent_rooms(garage, d.wall, fr)]
    assert inner, "garage needs a person door into the house"
    for d in inner:
        assert d.width <= 1.0, "interior garage door must be person-sized, not the gate"
        target = _door_target(garage, d, fr)
        assert target is not None
        assert target.room_type not in {
            RoomType.BATHROOM,
            RoomType.TOILET,
            RoomType.BEDROOM,
        }, f"garage person door opens into {target.room_type.value}"


def test_garage_gate_does_not_collide_with_window():
    garage, _ = _garage_and_floor(_gen(GARAGE_HEAVY))
    for w in garage.windows:
        for d in garage.doors:
            if d.wall != w.wall:
                continue
            clear = w.position + w.width <= d.position + 1e-6 or w.position >= (
                d.position + d.width - 1e-6
            )
            assert clear, f"window overlaps door on wall {w.wall}"


def test_garage_stays_on_ground_floor_in_two_storey():
    params = BuildingParams(rooms=GARAGE_HEAVY, country=CountryCode.RU, floors=2)
    rooms = LayoutEngine(params, GEO).generate()
    garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
    assert garage.floor == min(r.floor for r in rooms), "cars do not climb stairs"


def test_garage_with_open_plan_keeps_gate_and_only_flags_buffer():
    # Open plan puts the social zone (living+kitchen) up front, so this
    # garage-heavy program's garage band abuts the bedroom/wet band with no
    # buffer beside it. The honest outcome is a single rule-10 flag ("opens into
    # bathroom — add a mudroom"); everything else stays clean, gate intact.
    params = BuildingParams(
        rooms=GARAGE_HEAVY, country=CountryCode.RU, floors=1, openness="open"
    )
    rooms = LayoutEngine(params, GEO).generate()
    violations = check_invariants(rooms, openness="open")
    non_garage = [v for v in violations if v.rule != 10]
    assert non_garage == [], [f"{v.rule}: {v.message}" for v in non_garage]
    garage = next(r for r in rooms if r.room_type == RoomType.GARAGE)
    assert any(d.kind == "gate" for d in garage.doors)


def test_gate_survives_rotation():
    from core.orientation import rotate_layout

    rooms = _gen(GARAGE_HEAVY)
    rotate_layout(rooms, 1)
    garage, fr = _garage_and_floor(rooms)
    gates = [d for d in garage.doors if d.kind == "gate"]
    assert len(gates) == 1, "rotation must carry the gate, not clear or duplicate it"
    assert not _adjacent_rooms(garage, gates[0].wall, fr), "rotated gate must stay external"
