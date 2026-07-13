"""DXF export (release 4): the bridge to CIS engineers' AutoCAD workflow.

The DXF mirrors the 2D plan the canvas and PDF already show — the same
axis-line w×d geometry (walls not offset, documented), millimetres as drawing
units (the CIS CAD convention), proper layers (WALLS/DOORS/WINDOWS/LABELS),
localized room labels via the same helper the PDF uses. Verified by parsing
the emitted file back with ezdxf, not by trusting the writer.
"""

import io

import ezdxf
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

PROGRAM = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 20},
        {"room_type": "kitchen", "area_m2": 10},
        {"room_type": "bedroom", "area_m2": 14},
        {"room_type": "bathroom", "area_m2": 5},
        {"room_type": "toilet", "area_m2": 2},
        {"room_type": "hallway", "area_m2": 6},
    ],
    "country": "KZ",
    "floors": 2,
    "building_shape": "rectangular",
}


def _generate() -> dict:
    r = client.post("/api/v1/generate-plan", json=PROGRAM)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _fetch_doc(project_id: str, lang: str = "ru"):
    r = client.get(f"/api/v1/dxf/{project_id}?lang={lang}")
    assert r.status_code == 200, r.text[:300]
    assert "dxf" in r.headers["content-disposition"]
    return ezdxf.read(io.StringIO(r.content.decode("utf-8")))


def test_dxf_round_trips_the_plan():
    body = _generate()
    doc = _fetch_doc(body["project_id"])
    msp = doc.modelspace()

    walls = [e for e in msp if e.dxf.layer == "WALLS"]
    labels = [e for e in msp if e.dxf.layer == "LABELS" and e.dxftype() in ("TEXT", "MTEXT")]
    # One closed outline per room, plus per-floor captions in LABELS.
    assert len(walls) == len(body["rooms"])
    assert len(labels) >= len(body["rooms"])

    # Millimetre units: the widest room must measure thousands of units.
    widest = max(r["width"] for r in body["rooms"])
    xs = [v[0] for e in walls for v in e.get_points()]
    assert max(xs) - min(xs) >= widest * 1000 - 1


def test_dxf_labels_are_localized():
    body = _generate()
    doc = _fetch_doc(body["project_id"], lang="ru")
    texts = " ".join(
        e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"
    )
    assert "Кухня" in texts
    assert "Гостиная" in texts


def test_dxf_has_openings_layers():
    body = _generate()
    doc = _fetch_doc(body["project_id"])
    msp = doc.modelspace()
    doors = [e for e in msp if e.dxf.layer == "DOORS"]
    windows = [e for e in msp if e.dxf.layer == "WINDOWS"]
    total_doors = sum(len(r["doors"]) for r in body["rooms"])
    total_windows = sum(len(r["windows"]) for r in body["rooms"])
    assert total_doors > 0 and total_windows > 0
    assert len(doors) >= total_doors  # at least one entity per opening
    assert len(windows) >= total_windows


def test_dxf_404_for_unknown_project():
    r = client.get("/api/v1/dxf/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
