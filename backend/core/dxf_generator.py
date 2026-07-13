"""DXF export of the 2D plan — the bridge to CIS engineers' AutoCAD workflow.

Same axis-line w×d geometry as the canvas and PDF (walls not offset —
documented), millimetres as drawing units (the CIS CAD convention), layers
WALLS / DOORS / WINDOWS / LABELS. Floors sit side by side in one modelspace
with a caption each. A sketch handoff, not working drawings.
"""

import io

import ezdxf
from ezdxf.enums import TextEntityAlignment

from core.pdf_generator import _room_label
from models import GenerationResult

MM = 1000.0  # model units are mm; engine geometry is metres
FLOOR_GAP_MM = 3000.0
TEXT_H = 250.0
CAPTION_H = 400.0

_FLOOR_CAPTION = {"en": "Floor", "ru": "Этаж", "kk": "Қабат"}

_LAYERS = (
    ("WALLS", 7),  # white/black
    ("DOORS", 1),  # red
    ("WINDOWS", 5),  # blue
    ("LABELS", 8),  # grey
)


def _opening(msp, spec, x: float, y: float, rw: float, rd: float, layer: str) -> None:
    """One line along the host wall spanning the opening width.

    Wall convention matches the engine: S = min-y edge, N = max-y, W = min-x,
    E = max-x; position is the offset from the west/south corner.
    """
    w = spec.width * MM
    pos = spec.position * MM
    if spec.wall == "S":
        p1, p2 = (x + pos, y), (x + pos + w, y)
    elif spec.wall == "N":
        p1, p2 = (x + pos, y + rd), (x + pos + w, y + rd)
    elif spec.wall == "W":
        p1, p2 = (x, y + pos), (x, y + pos + w)
    else:  # E
        p1, p2 = (x + rw, y + pos), (x + rw, y + pos + w)
    msp.add_line(p1, p2, dxfattribs={"layer": layer})


def generate_dxf(result: GenerationResult, lang: str = "en") -> str:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # millimetres
    for name, color in _LAYERS:
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    offset_x = 0.0
    for f in sorted({r.floor for r in result.rooms}):
        rooms = [r for r in result.rooms if r.floor == f]
        min_x = min(r.x for r in rooms)
        min_y = min(r.y for r in rooms)
        floor_w = (max(r.x + r.width for r in rooms) - min_x) * MM

        for room in rooms:
            x = (room.x - min_x) * MM + offset_x
            y = (room.y - min_y) * MM
            rw, rd = room.width * MM, room.depth * MM
            msp.add_lwpolyline(
                [(x, y), (x + rw, y), (x + rw, y + rd), (x, y + rd)],
                close=True,
                dxfattribs={"layer": "WALLS"},
            )
            # The same actual-footprint figure every other surface shows.
            label = f"{_room_label(room, lang)} {room.width * room.depth:.1f} m2"
            msp.add_text(
                label, height=TEXT_H, dxfattribs={"layer": "LABELS"}
            ).set_placement((x + rw / 2, y + rd / 2), align=TextEntityAlignment.MIDDLE_CENTER)
            for d in room.doors:
                _opening(msp, d, x, y, rw, rd, "DOORS")
            for wnd in room.windows:
                _opening(msp, wnd, x, y, rw, rd, "WINDOWS")

        caption = f"{_FLOOR_CAPTION.get(lang, _FLOOR_CAPTION['en'])} {f}"
        msp.add_text(
            caption, height=CAPTION_H, dxfattribs={"layer": "LABELS"}
        ).set_placement((offset_x + floor_w / 2, -2.5 * CAPTION_H), align=TextEntityAlignment.MIDDLE_CENTER)
        offset_x += floor_w + FLOOR_GAP_MM

    out = io.StringIO()
    doc.write(out)
    return out.getvalue()
