"""
PDF report generator for a completed GenerationResult.
Renders a localized (en/ru/kk) summary: rooms, geo-climate, cost,
compliance and MEP findings, with a non-liability disclaimer.
"""

import io
import logging
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import GenerationResult

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
        "rooms": "Rooms",
        "room": "Room",
        "floor": "Floor",
        "dims": "Dimensions",
        "area": "Area",
        "cost": "Cost Estimate",
        "total_usd": "Total (USD)",
        "total_local": "Total (local)",
        "concrete": "Concrete",
        "brick": "Brick",
        "insul_m2": "Insulation",
        "compliance": "Compliance Issues",
        "no_issues": "All checked rules passed.",
        "fix": "Fix",
        "mep": "MEP Conflicts",
        "no_clashes": "No MEP clashes detected.",
        "warnings": "Warnings",
        "disclaimer": "Schematic design for preliminary assessment only. "
        "Requires certification by a licensed architect.",
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
        "rooms": "Помещения",
        "room": "Помещение",
        "floor": "Этаж",
        "dims": "Размеры",
        "area": "Площадь",
        "cost": "Смета",
        "total_usd": "Итого (USD)",
        "total_local": "Итого (местная валюта)",
        "concrete": "Бетон",
        "brick": "Кирпич",
        "insul_m2": "Утеплитель",
        "compliance": "Замечания по нормам",
        "no_issues": "Все проверенные нормы соблюдены.",
        "fix": "Рекомендация",
        "mep": "Конфликты инженерных сетей",
        "no_clashes": "Конфликтов инженерных сетей не обнаружено.",
        "warnings": "Предупреждения",
        "disclaimer": "Эскизный проект для предварительной оценки. "
        "Требует заверения лицензированным архитектором.",
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
        "rooms": "Бөлмелер",
        "room": "Бөлме",
        "floor": "Қабат",
        "dims": "Өлшемдері",
        "area": "Ауданы",
        "cost": "Смета",
        "total_usd": "Барлығы (USD)",
        "total_local": "Барлығы (жергілікті валюта)",
        "concrete": "Бетон",
        "brick": "Кірпіш",
        "insul_m2": "Жылу оқшаулағыш",
        "compliance": "Нормалар бойынша ескертулер",
        "no_issues": "Барлық тексерілген талаптар орындалды.",
        "fix": "Ұсыныс",
        "mep": "Инженерлік желілер қақтығыстары",
        "no_clashes": "Инженерлік желілер қақтығысы табылмады.",
        "warnings": "Ескертулер",
        "disclaimer": "Алдын ала бағалауға арналған эскиздік жоба. "
        "Лицензияланған сәулетшінің растауын қажет етеді.",
    },
}


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

    # Rooms
    story.append(Paragraph(t["rooms"], styles["h2"]))
    rows = [[t["room"], t["floor"], t["dims"], t["area"]]]
    for r in sorted(result.rooms, key=lambda r: (r.floor, r.name)):
        rows.append(
            [r.name, str(r.floor), f"{r.width:.2f} × {r.depth:.2f} m", f"{r.area_m2:.1f} m²"]
        )
    story.append(Table(rows, colWidths=[70 * mm, 20 * mm, 45 * mm, 25 * mm], style=_TABLE_STYLE))

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
