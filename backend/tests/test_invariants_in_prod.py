"""Invariant violations must reach the API response.

check_invariants() used to run only in tests: the engine could ship a house
where no room was livable (living room 1.8 m deep, garage 1.47 m) while the
response carried zero compliance issues — a green badge on an unusable plan.
The route now mirrors every violation into compliance_issues as an ERROR.

The anchor scenario is the real bug report: budget spaciousness + a 12 m plot
+ garage + two bedrooms collapsed every band to 1.5–2.0 m depth.
"""

from fastapi.testclient import TestClient

from core.layout_engine import USABLE_MIN_SIDE
from main import app
from models import RoomType

client = TestClient(app)

COLLAPSED_BUDGET_PLAN = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 18},
        {"room_type": "kitchen", "area_m2": 9},
        {"room_type": "bedroom", "area_m2": 12},
        {"room_type": "bedroom", "area_m2": 12},
        {"room_type": "bathroom", "area_m2": 4},
        {"room_type": "toilet", "area_m2": 1.5},
        {"room_type": "hallway", "area_m2": 6},
        {"room_type": "garage", "area_m2": 22},
    ],
    "country": "KZ",
    "floors": 1,
    "plot_width_m": 12.0,
    "building_shape": "rectangular",
    "openness": "mixed",
    "spaciousness": 0.0,
}


def test_unlivable_rooms_cannot_ship_green():
    r = client.post("/api/v1/generate-plan", json=COLLAPSED_BUDGET_PLAN)
    assert r.status_code == 200, r.text[:300]
    body = r.json()

    shortfalls = [
        room
        for room in body["rooms"]
        if min(room["width"], room["depth"])
        < USABLE_MIN_SIDE.get(RoomType(room["room_type"]), 0.0) - 0.01
    ]
    narrow_issues = [
        i for i in body["compliance_issues"] if i["rule_id"].startswith("INV-9")
    ]

    if shortfalls:
        # Engine still produces sub-minimum rooms here (until the stacking
        # fix lands) — then EVERY one of them must be named in a red issue.
        flagged = {i.get("room_id") for i in narrow_issues}
        for room in shortfalls:
            assert room["room_id"] in flagged, (
                f"{room['room_type']} is {room['width']}x{room['depth']} "
                "but ships without a compliance ERROR — green badge lie"
            )
        assert all(i["severity"] == "ERROR" for i in narrow_issues)
        # The message must say WHAT is wrong, not just flag the room.
        assert all("needs" in i["description"] for i in narrow_issues)
    else:
        # Engine got fixed and this plan is livable — no phantom red allowed.
        assert narrow_issues == []


def test_all_invariant_rules_are_mirrored_not_just_rule9():
    r = client.post("/api/v1/generate-plan", json=COLLAPSED_BUDGET_PLAN)
    assert r.status_code == 200
    from core.plan_invariants import check_invariants
    from models import RoomLayout

    body = r.json()
    rooms = [RoomLayout(**rm) for rm in body["rooms"]]
    violations = check_invariants(rooms, openness="mixed")
    mirrored = {i["rule_id"] for i in body["compliance_issues"] if i["rule_id"].startswith("INV-")}
    for v in violations:
        assert f"INV-{v.rule}-{v.code.upper()}" in mirrored
