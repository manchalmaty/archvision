"""
PDF report generator for a completed GenerationResult.
Renders a localized (en/ru/kk) summary: rooms, geo-climate, cost,
compliance and MEP findings, with a non-liability disclaimer.
"""

import io
import logging
import math
import os
from datetime import date

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.geo_calculator import SEISMIC_ADVISORY_ZONE
from models import GenerationResult, RoomLayout

logger = logging.getLogger(__name__)

# ── Cyrillic-capable font discovery ──────────────────────────────────────────
# ReportLab's built-in Type1 fonts (Helvetica) have no Cyrillic glyphs, so we
# register a system TTF. Order matters: first hit wins.
_FONT_CANDIDATES = [
    # (regular, bold)
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
]

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
for _reg, _bold in _FONT_CANDIDATES:
    if os.path.exists(_reg):
        try:
            pdfmetrics.registerFont(TTFont("AVSans", _reg))
            FONT = "AVSans"
            if os.path.exists(_bold):
                pdfmetrics.registerFont(TTFont("AVSans-Bold", _bold))
                FONT_BOLD = "AVSans-Bold"
            else:
                FONT_BOLD = "AVSans"
            break
        except Exception:
            continue

if FONT == "Helvetica":
    # Built-in Type1 fonts have no Cyrillic glyphs — ru/kk reports will show
    # boxes. Surface it loudly so a missing font package is caught in ops.
    logger.warning(
        "No Cyrillic-capable TTF font found (checked %d locations); "
        "ru/kk PDF reports will render Cyrillic as boxes. "
        "Install fonts-dejavu-core or equivalent.",
        len(_FONT_CANDIDATES),
    )

# ── Localized labels ─────────────────────────────────────────────────────────
_L = {
    "en": {
        "title": "Architectural Draft Report",
        "project": "Project",
        "generated": "Generated",
        "geo": "Geo-Climate & Structural Data",
        "frost": "Frost depth",
        "seismic": "Seismic zone",
        "wall": "Wall thickness",
        "insul": "Insulation",
        "snow": "Snow load",
        "wind": "Wind load",
        "foundation": "Foundation type",
        "plan": "Floor Plan",
        "rooms": "Rooms",
        "room": "Room",
        "floor": "Floor",
        "dims": "Dimensions",
        "area": "Area",
        "net_area": "Net (usable)",
        "cost": "Cost Estimate",
        "total_usd": "Total (USD)",
        "total_local": "Total (local)",
        "concrete": "Concrete",
        "brick": "Brick",
        "insul_m2": "Insulation",
        "compliance": "Preliminary Checks (not a code review)",
        "no_issues": "Areas and geometry checked. Building codes (SNiP/SP) "
        "require review by a licensed specialist.",
        "fix": "Fix",
        "mep": "MEP Conflicts",
        "no_clashes": "No clashes found. Checked: water riser and branches (draft).",
        "warnings": "Warnings",
        "disclaimer": "Draft layout and rough cost estimate — arrive at your "
        "architect prepared. Not construction documents.",
        "seismic_advisory": "High seismicity (zone {zone}): a reinforced-concrete "
        "frame / monolithic foundation and a specialist's review are required — a "
        "strip foundation is not enough, and the frame raises the estimate (priced "
        "by an engineer). Exact intensity: the ОСР/СНиП map for your site.",
        "seismic_unverified": "Seismicity NOT verified for this location — the "
        "region is not in our database, so the values above are the country "
        "average and may read low. Determine the real zone from the ОСР/СНиП map "
        "for the site before relying on the foundation or the estimate.",
    },
    "ru": {
        "title": "Отчёт по архитектурному эскизу",
        "project": "Проект",
        "generated": "Сформирован",
        "geo": "Геоклимат и конструктив",
        "frost": "Глубина промерзания",
        "seismic": "Сейсмическая зона",
        "wall": "Толщина стен",
        "insul": "Утеплитель",
        "snow": "Снеговая нагрузка",
        "wind": "Ветровая нагрузка",
        "foundation": "Тип фундамента",
        "plan": "План этажа",
        "rooms": "Помещения",
        "room": "Помещение",
        "floor": "Этаж",
        "dims": "Размеры",
        "area": "Площадь",
        "net_area": "Полезная",
        "cost": "Смета",
        "total_usd": "Итого (USD)",
        "total_local": "Итого (местная валюта)",
        "concrete": "Бетон",
        "brick": "Кирпич",
        "insul_m2": "Утеплитель",
        "compliance": "Предварительная проверка (не проверка норм)",
        "no_issues": "Площади и геометрия проверены. Проверка норм (СНиП/СП) — "
        "у лицензированного специалиста.",
        "fix": "Рекомендация",
        "mep": "Конфликты инженерных сетей",
        "no_clashes": "Конфликтов не найдено. Проверено: стояк и разводка воды (черновик).",
        "warnings": "Предупреждения",
        "disclaimer": "Черновая планировка и ориентировочная смета — чтобы прийти "
        "к архитектору подготовленным. Не проектная документация.",
        "seismic_advisory": "Высокая сейсмичность (зона {zone}): нужен ж/б каркас / "
        "монолитный фундамент и проверка специалистом — ленточного недостаточно, "
        "а каркас удорожает смету (оценивает инженер). Точный балл — по карте "
        "ОСР/СНиП для участка.",
        "seismic_unverified": "Сейсмичность НЕ подтверждена для этого места — "
        "региона нет в базе, поэтому значения выше — средние по стране и могут быть "
        "занижены. Определите реальную зону по карте ОСР/СНиП для участка, прежде "
        "чем полагаться на фундамент или смету.",
    },
    "kk": {
        "title": "Сәулеттік эскиз бойынша есеп",
        "project": "Жоба",
        "generated": "Құрылған күні",
        "geo": "Геоклимат және конструкция",
        "frost": "Қату тереңдігі",
        "seismic": "Сейсмикалық аймақ",
        "wall": "Қабырға қалыңдығы",
        "insul": "Жылу оқшаулағыш",
        "snow": "Қар жүктемесі",
        "wind": "Жел жүктемесі",
        "foundation": "Іргетас түрі",
        "plan": "Қабат жоспары",
        "rooms": "Бөлмелер",
        "room": "Бөлме",
        "floor": "Қабат",
        "dims": "Өлшемдері",
        "area": "Ауданы",
        "net_area": "Пайдалы",
        "cost": "Смета",
        "total_usd": "Барлығы (USD)",
        "total_local": "Барлығы (жергілікті валюта)",
        "concrete": "Бетон",
        "brick": "Кірпіш",
        "insul_m2": "Жылу оқшаулағыш",
        "compliance": "Алдын ала тексеру (нормалар тексерісі емес)",
        "no_issues": "Аудандар мен геометрия тексерілді. Нормаларды (ҚНжЕ) тексеру — "
        "лицензияланған маманда.",
        "fix": "Ұсыныс",
        "mep": "Инженерлік желілер қақтығыстары",
        "no_clashes": "Қақтығыстар табылмады. Тексерілді: су тірегі мен тарату (черновик).",
        "warnings": "Ескертулер",
        "disclaimer": "Черновой жоспарлау және шамамен смета — сәулетшіге дайын "
        "болып бару үшін. Жобалық құжаттама емес.",
        "seismic_advisory": "Жоғары сейсмикалық (аймақ {zone}): темірбетон қаңқа / "
        "монолитті іргетас және маман тексеруі қажет — таспалы іргетас жеткіліксіз, "
        "ал қаңқа сметаны қымбаттатады (инженер бағалайды). Нақты балл — учаске "
        "бойынша ОСР/СНиП картасынан.",
        "seismic_unverified": "Бұл жер үшін сейсмикалық ЖОҚ расталмаған — аймақ "
        "базада жоқ, сондықтан жоғарыдағы мәндер — ел бойынша орташа және төмен "
        "болуы мүмкін. Іргетасқа не сметаға сенбес бұрын нақты аймақты учаске "
        "бойынша ОСР/СНиП картасынан анықтаңыз.",
    },
}


# Room-type display labels, matched to the frontend i18n `roomTypes.*` so the PDF
# reads the same as the on-screen plan. The layout engine stores either a user's
# custom name or the English-title default of the type (name = custom or
# room_type.title()); we localize the latter and keep the former verbatim.
_ROOM_LABELS = {
    "en": {
        "living_room": "Living Room",
        "bedroom": "Bedroom",
        "kitchen": "Kitchen",
        "bathroom": "Bathroom",
        "toilet": "Toilet",
        "hallway": "Hallway",
        "utility": "Utility Room",
        "garage": "Garage",
    },
    "ru": {
        "living_room": "Гостиная",
        "bedroom": "Спальня",
        "kitchen": "Кухня",
        "bathroom": "Ванная",
        "toilet": "Туалет",
        "hallway": "Прихожая",
        "utility": "Хозяйственная",
        "garage": "Гараж",
    },
    "kk": {
        "living_room": "Қонақ бөлме",
        "bedroom": "Жатын бөлме",
        "kitchen": "Ас үй",
        "bathroom": "Жуынатын бөлме",
        "toilet": "Дәретхана",
        "hallway": "Дәліз",
        "utility": "Шаруашылық бөлме",
        "garage": "Гараж",
    },
}


def _room_label(room: RoomLayout, lang: str) -> str:
    """Localize a generated room name; keep a user's custom name verbatim."""
    default_en = room.room_type.value.replace("_", " ").title()
    if room.name and room.name != default_en:
        return room.name
    return _ROOM_LABELS.get(lang, _ROOM_LABELS["en"]).get(room.room_type.value, default_en)


def _table_style(*extra: tuple) -> TableStyle:
    """Shared base look for every table; pass per-table overrides as extras."""
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b7c3")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            *extra,
        ]
    )


# Header row bolded and tinted — used by the rooms table.
_TABLE_STYLE = _table_style(
    ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf2")),
)


_INK = colors.HexColor("#1f2937")
_ROOM_FILL = colors.HexColor("#f8fafc")
_LABEL = colors.HexColor("#111827")
_MUTED = colors.HexColor("#6b7280")
_WINDOW = colors.HexColor("#2563eb")
_DOOR = colors.HexColor("#94a3b8")
_PLAN_WALL_PT = 1.8
_PLAN_MAX_H = 105 * mm


def _door_world(r: RoomLayout, door):
    """Opening endpoints (a, b), the into-room unit normal, and width — in world
    metres. World y grows downward (matches the layout engine)."""
    p, dw = door.position, door.width
    if door.wall == "S":
        return (r.x + p, r.y), (r.x + p + dw, r.y), (0.0, 1.0), dw
    if door.wall == "N":
        return (r.x + p, r.y + r.depth), (r.x + p + dw, r.y + r.depth), (0.0, -1.0), dw
    if door.wall == "W":
        return (r.x, r.y + p), (r.x, r.y + p + dw), (1.0, 0.0), dw
    return (r.x + r.width, r.y + p), (r.x + r.width, r.y + p + dw), (-1.0, 0.0), dw


def _floor_plan_drawing(
    rooms: list[RoomLayout], avail_w: float, caption: str, lang: str = "en"
) -> Drawing:
    """Vector floor plan: poché walls, doors (swing arc), windows and labels."""
    min_x = min(r.x for r in rooms)
    min_y = min(r.y for r in rooms)
    max_x = max(r.x + r.width for r in rooms)
    max_y = max(r.y + r.depth for r in rooms)
    plan_w, plan_h = max_x - min_x, max_y - min_y
    pad, cap_h = 6.0, 14.0
    scale = min((avail_w - 2 * pad) / plan_w, (_PLAN_MAX_H - 2 * pad - cap_h) / plan_h)
    dw_pt = plan_w * scale + 2 * pad
    dh_pt = plan_h * scale + 2 * pad + cap_h
    d = Drawing(dw_pt, dh_pt)

    def sx(wx: float) -> float:
        return pad + (wx - min_x) * scale

    def sy(wy: float) -> float:  # flip so north (smaller world y) is up
        return cap_h + pad + (max_y - wy) * scale

    for r in rooms:
        d.add(
            Rect(
                sx(r.x),
                sy(r.y + r.depth),
                r.width * scale,
                r.depth * scale,
                fillColor=_ROOM_FILL,
                strokeColor=_INK,
                strokeWidth=_PLAN_WALL_PT,
            )
        )

    for r in rooms:
        for win in r.windows:
            (ax, ay), (bx, by), _, _ = _door_world(r, win)
            d.add(Line(sx(ax), sy(ay), sx(bx), sy(by), strokeColor=_WINDOW, strokeWidth=2.2))
        for door in r.doors:
            (ax, ay), (bx, by), (nx, ny), dwm = _door_world(r, door)
            # erase the wall under the opening
            d.add(
                Line(
                    sx(ax),
                    sy(ay),
                    sx(bx),
                    sy(by),
                    strokeColor=_ROOM_FILL,
                    strokeWidth=_PLAN_WALL_PT + 1.2,
                )
            )
            kind = getattr(door, "kind", "door")
            if kind == "opening":
                # Cased gap: jamb ticks only — a swing arc here would draw a
                # 2-3 m door leaf that cannot physically exist.
                t = 0.10
                for px, py in ((ax, ay), (bx, by)):
                    d.add(
                        Line(
                            sx(px - nx * t),
                            sy(py - ny * t),
                            sx(px + nx * t),
                            sy(py + ny * t),
                            strokeColor=_INK,
                            strokeWidth=0.8,
                        )
                    )
                continue
            if kind == "gate":
                # Sectional/roll-up gate: straight panel inset into the room.
                inset = 0.15
                d.add(
                    Line(
                        sx(ax + nx * inset),
                        sy(ay + ny * inset),
                        sx(bx + nx * inset),
                        sy(by + ny * inset),
                        strokeColor=_DOOR,
                        strokeWidth=1.4,
                    )
                )
                continue
            a0 = math.atan2(by - ay, bx - ax)
            a1 = math.atan2(ny, nx)
            if a1 - a0 > math.pi:
                a1 -= 2 * math.pi
            elif a0 - a1 > math.pi:
                a1 += 2 * math.pi
            pts = []
            for i in range(9):
                ang = a0 + (a1 - a0) * i / 8
                pts += [sx(ax + dwm * math.cos(ang)), sy(ay + dwm * math.sin(ang))]
            d.add(PolyLine(pts, strokeColor=_DOOR, strokeWidth=0.5))
            d.add(
                Line(
                    sx(ax),
                    sy(ay),
                    sx(ax + nx * dwm),
                    sy(ay + ny * dwm),
                    strokeColor=_DOOR,
                    strokeWidth=0.9,
                )
            )

    for r in rooms:
        cx, cy = sx(r.x + r.width / 2), sy(r.y + r.depth / 2)
        d.add(
            String(
                cx,
                cy + 2,
                _room_label(r, lang),
                textAnchor="middle",
                fontName=FONT_BOLD,
                fontSize=7,
                fillColor=_LABEL,
            )
        )
        d.add(
            String(
                cx,
                cy - 7,
                f"{r.width * r.depth:.1f} m²",
                textAnchor="middle",
                fontName=FONT,
                fontSize=6,
                fillColor=_MUTED,
            )
        )

    d.add(
        String(pad, 4, caption, fontName=FONT, fontSize=7.5, fillColor=colors.HexColor("#374151"))
    )
    return d


def generate_pdf(result: GenerationResult, lang: str = "en") -> bytes:
    """Render the report and return raw PDF bytes."""
    t = _L.get(lang, _L["en"])

    styles = {
        "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=16, spaceAfter=2 * mm),
        "h2": ParagraphStyle(
            "h2", fontName=FONT_BOLD, fontSize=12, spaceBefore=5 * mm, spaceAfter=2 * mm
        ),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12),
        "muted": ParagraphStyle(
            "muted", fontName=FONT, fontSize=8, textColor=colors.HexColor("#667085")
        ),
        "warn": ParagraphStyle(
            "warn", fontName=FONT, fontSize=8.5, leading=11.5,
            textColor=colors.HexColor("#8a5a12"), spaceBefore=1.5 * mm,
        ),
    }

    story = []
    story.append(Paragraph(t["title"], styles["h1"]))
    story.append(
        Paragraph(
            f'{t["project"]}: <font face="{FONT}">{result.project_id[:8]}</font> · '
            f'{t["generated"]}: {date.today().isoformat()}',
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    # Floor plan drawing(s) — the actual 2D scheme, one per floor
    avail_w = A4[0] - 36 * mm  # page width minus left+right margins
    floors = sorted({r.floor for r in result.rooms})
    if result.rooms:
        story.append(Paragraph(t["plan"], styles["h2"]))
        for f in floors:
            fr = [r for r in result.rooms if r.floor == f]
            area = sum(r.width * r.depth for r in fr)
            caption = f"{t['floor']} {f} · {area:.1f} m²"
            try:
                story.append(_floor_plan_drawing(fr, avail_w, caption, lang))
                story.append(Spacer(1, 3 * mm))
            except Exception:
                logger.exception("Failed to render floor plan for floor %s", f)

    # Geo-climate
    g = result.geo_climate
    story.append(Paragraph(t["geo"], styles["h2"]))
    story.append(
        Table(
            [
                [t["frost"], f"{g.frost_depth_m} m", t["seismic"], str(g.seismic_zone)],
                [
                    t["wall"],
                    f"{g.wall_thickness_mm} mm",
                    t["insul"],
                    f"{g.insulation_thickness_mm} mm",
                ],
                [t["snow"], f"{g.snow_load_kpa} kPa", t["wind"], f"{g.wind_load_kpa} kPa"],
                [t["foundation"], g.foundation_type, "", ""],
            ],
            colWidths=[42 * mm, 38 * mm, 42 * mm, 38 * mm],
            style=_table_style(("SPAN", (1, 3), (3, 3))),
        )
    )
    # Unverified location comes first: an unlisted town gets the country-average
    # zone, which reads low for a high-seismic area — say so before the number
    # can be trusted.
    if not result.region_recognized:
        story.append(Paragraph(f"⚠ {t['seismic_unverified']}", styles["warn"]))
    # High-seismicity safety advisory — soft, references the ОСР/СНиП map for the
    # exact intensity rather than asserting an MSK score this tool doesn't know.
    if g.seismic_zone >= SEISMIC_ADVISORY_ZONE:
        story.append(Paragraph(f"⚠ {t['seismic_advisory'].format(zone=g.seismic_zone)}", styles["warn"]))

    # Rooms
    story.append(Paragraph(t["rooms"], styles["h2"]))
    rows = [[t["room"], t["floor"], t["dims"], t["area"], t["net_area"]]]
    for r in sorted(result.rooms, key=lambda r: (r.floor, _room_label(r, lang))):
        rows.append(
            [
                _room_label(r, lang),
                str(r.floor),
                f"{r.width:.2f} × {r.depth:.2f} m",
                f"{r.width * r.depth:.1f} m²",
                # Net figure exists only on post-release-5 results.
                f"{r.net_area:.1f} m²" if r.net_area is not None else "—",
            ]
        )
    story.append(
        Table(rows, colWidths=[55 * mm, 15 * mm, 40 * mm, 25 * mm, 25 * mm], style=_TABLE_STYLE)
    )

    # Cost
    c = result.cost_estimate
    story.append(Paragraph(t["cost"], styles["h2"]))
    cost_rows = [
        [t["total_usd"], f"${c.total_cost_usd:,.0f}"],
        [t["total_local"], f"{c.total_cost_local:,.0f} {c.currency}"],
        [t["concrete"], f"{c.concrete_m3} m³"],
        [t["brick"], f"{c.brick_m3} m³"],
        [t["insul_m2"], f"{c.insulation_m2} m²"],
    ]
    for k, v in c.breakdown.items():
        cost_rows.append([k.replace("_usd", "").replace("_", " ").title(), f"${v:,.0f}"])
    # Both total rows (USD and local currency) are intentionally bold.
    story.append(
        Table(
            cost_rows,
            colWidths=[90 * mm, 70 * mm],
            style=_table_style(("FONTNAME", (0, 0), (-1, 1), FONT_BOLD)),
        )
    )

    # Compliance
    story.append(Paragraph(t["compliance"], styles["h2"]))
    if not result.compliance_issues:
        story.append(Paragraph(t["no_issues"], styles["body"]))
    else:
        for issue in result.compliance_issues:
            text = f"<b>[{issue.severity}]</b> {issue.description}"
            if issue.suggested_fix:
                text += f"<br/>→ {t['fix']}: {issue.suggested_fix}"
            story.append(Paragraph(text, styles["body"]))
            story.append(Spacer(1, 1.5 * mm))

    # MEP
    story.append(Paragraph(t["mep"], styles["h2"]))
    if not result.mep_conflicts:
        story.append(Paragraph(t["no_clashes"], styles["body"]))
    else:
        for conf in result.mep_conflicts:
            story.append(
                Paragraph(
                    f"<b>[{conf.severity}]</b> {conf.description} "
                    f"({conf.location_x:.1f}, {conf.location_y:.1f}, {conf.location_z:.1f})",
                    styles["body"],
                )
            )
            story.append(Spacer(1, 1.5 * mm))

    # Warnings
    if result.warnings:
        story.append(Paragraph(t["warnings"], styles["h2"]))
        for w in result.warnings:
            story.append(Paragraph(f"⚠ {w}", styles["body"]))
            story.append(Spacer(1, 1.5 * mm))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(t["disclaimer"], styles["muted"]))

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=t["title"],
    ).build(story)
    return buf.getvalue()
