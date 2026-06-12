"""
End-to-end smoke test: boots the FastAPI app in-process (TestClient),
generates a plan, checks layout invariants, and downloads the PDF report.
Run: .venv/Scripts/python smoke_e2e.py
"""

import os

# Keep the smoke test offline: no Groq enrichment.
os.environ["GROQ_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)

params = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 20},
        {"room_type": "bedroom", "area_m2": 14},
        {"room_type": "kitchen", "area_m2": 10},
        {"room_type": "bathroom", "area_m2": 5},
        {"room_type": "toilet", "area_m2": 2},
        {"room_type": "hallway", "area_m2": 6},
    ],
    "country": "KZ",
    "region": "Алматы",
    "floors": 2,
    "plot_width_m": 9.0,
    "plot_depth_m": 12.0,
    "building_shape": "rectangular",
}

print("POST /generate-plan ...")
r = client.post("/api/v1/generate-plan", json=params)
assert r.status_code == 200, f"generate failed: {r.status_code} {r.text[:300]}"
res = r.json()
pid = res["project_id"]
print(
    f"  project {pid[:8]}: {len(res['rooms'])} rooms, "
    f"{len(res['mep_conflicts'])} MEP conflicts, "
    f"{len(res['compliance_issues'])} compliance issues, "
    f"warnings={res['warnings']}"
)

# Plot-width invariant: strip packer must respect plot width
max_x = max(rm["x"] + rm["width"] for rm in res["rooms"])
print(f"  building width {max_x:.2f} m vs plot {params['plot_width_m']} m")
assert max_x <= params["plot_width_m"] + 0.01, "plot width constraint violated"

# Rooms must not overlap (same floor, AABB check)
rooms = res["rooms"]
for i, a in enumerate(rooms):
    for b in rooms[i + 1 :]:
        if a["floor"] != b["floor"]:
            continue
        sep = (
            a["x"] + a["width"] <= b["x"] + 0.01
            or b["x"] + b["width"] <= a["x"] + 0.01
            or a["y"] + a["depth"] <= b["y"] + 0.01
            or b["y"] + b["depth"] <= a["y"] + 0.01
        )
        assert sep, f"rooms overlap: {a['name']} / {b['name']}"
print("  layout invariants OK (no overlaps, plot width respected)")

for lang in ("en", "ru", "kk"):
    r = client.get(f"/api/v1/report/{pid}", params={"lang": lang})
    assert r.status_code == 200, f"report {lang} failed: {r.status_code}"
    assert r.content[:5] == b"%PDF-", f"report {lang}: not a PDF"
    print(f"GET /report ({lang}): OK, {len(r.content)} bytes")

r = client.get(f"/api/v1/report/{pid}", params={"lang": "xx"})
assert r.status_code == 422, "invalid lang must be rejected"
r = client.get("/api/v1/report/00000000-dead-beef-0000-000000000000")
assert r.status_code == 404, "missing project must 404"
# Non-UUID ids (path-traversal shapes) must be rejected by validation
for bad in ("..", "%2e%2e", "not-a-uuid"):
    r = client.get(f"/api/v1/report/{bad}")
    assert r.status_code in (404, 422), f"non-UUID id {bad!r} must be rejected, got {r.status_code}"
    r = client.get(f"/api/v1/download/{bad}")
    assert r.status_code in (404, 422), f"non-UUID id {bad!r} must be rejected, got {r.status_code}"
print("report validation/404/traversal-guard OK")

print("\nE2E SMOKE TEST PASSED")
