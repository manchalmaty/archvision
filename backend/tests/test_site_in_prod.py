"""Site placement must reach the API response — figures and honest reds.

Mirrors the invariants-in-prod contract: the site planner is not a test-only
gadget. A plot size on the request must produce a `site` block in the result,
and any setback/coverage breach must surface as a red SITE-* compliance issue
(never a silent green).
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# A modest program on a generous plot: should place cleanly, no SITE reds.
ROOMY_PLOT = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 20},
        {"room_type": "bedroom", "area_m2": 14},
        {"room_type": "kitchen", "area_m2": 10},
        {"room_type": "bathroom", "area_m2": 5},
        {"room_type": "toilet", "area_m2": 2},
        {"room_type": "hallway", "area_m2": 6},
    ],
    "country": "KZ",
    "floors": 2,
    "plot_width_m": 25.0,
    "plot_depth_m": 30.0,
    "street_side": "S",
    "building_shape": "rectangular",
}


def _site_issues(body):
    return [i for i in body["compliance_issues"] if i["rule_id"].startswith("SITE-")]


def test_site_block_present_when_plot_given():
    r = client.post("/api/v1/generate-plan", json=ROOMY_PLOT)
    assert r.status_code == 200, r.text[:300]
    site = r.json()["site"]
    assert site is not None
    assert set(site["clearances"]) == {"S", "N", "W", "E"}
    assert site["coverage_ratio"] <= site["coverage_limit"]


def test_no_site_block_without_plot():
    body = {k: v for k, v in ROOMY_PLOT.items() if k not in ("plot_width_m", "plot_depth_m")}
    r = client.post("/api/v1/generate-plan", json=body)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["site"] is None


def test_roomy_plot_ships_no_site_reds():
    r = client.post("/api/v1/generate-plan", json=ROOMY_PLOT)
    assert _site_issues(r.json()) == []


def test_tight_plot_flags_coverage_red():
    # Same program crammed onto a small plot → footprint > 30% coverage.
    tight = {**ROOMY_PLOT, "floors": 1, "plot_width_m": 12.0, "plot_depth_m": 14.0}
    r = client.post("/api/v1/generate-plan", json=tight)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    reds = _site_issues(body)
    assert any(i["rule_id"].startswith("SITE-2") for i in reds), reds
    assert all(i["severity"] == "ERROR" for i in reds)
    # The message names WHAT is broken, not just a code.
    assert any("%" in i["description"] for i in reds)
