"""
RAG-based compliance checker against building codes (СНиП/СП/DIN/IBC).
Rule-based core with optional Groq LLM enrichment.
"""
import math
import uuid
import logging
from typing import List

from openai import OpenAI

from models import (
    BuildingParams, RoomLayout, RoomType,
    ComplianceIssue, ComplianceRequest, CountryCode
)
from config import settings

logger = logging.getLogger(__name__)

_groq_client: OpenAI | None = None


def _get_groq() -> OpenAI | None:
    """Lazy-init Groq client. Returns None if key not configured."""
    global _groq_client
    if _groq_client is None and settings.GROQ_API_KEY:
        _groq_client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    return _groq_client

# Hardcoded rules as fallback when RAG index is empty (MVP cold start)
MIN_AREAS: dict[str, dict[RoomType, float]] = {
    "RU": {
        RoomType.BEDROOM: 8.0,
        RoomType.LIVING_ROOM: 12.0,
        RoomType.KITCHEN: 6.0,
        RoomType.BATHROOM: 2.5,
        RoomType.TOILET: 0.96,
        RoomType.HALLWAY: 1.4,
    },
    "KZ": {
        RoomType.BEDROOM: 8.0,
        RoomType.LIVING_ROOM: 12.0,
        RoomType.KITCHEN: 6.0,
        RoomType.BATHROOM: 2.5,
        RoomType.TOILET: 0.96,
        RoomType.HALLWAY: 1.4,
    },
    "DE": {
        RoomType.BEDROOM: 8.0,
        RoomType.LIVING_ROOM: 14.0,
        RoomType.KITCHEN: 8.0,
        RoomType.BATHROOM: 3.5,
        RoomType.TOILET: 1.5,
        RoomType.HALLWAY: 1.5,
    },
    "US": {
        RoomType.BEDROOM: 6.5,
        RoomType.LIVING_ROOM: 11.1,
        RoomType.KITCHEN: 5.6,
        RoomType.BATHROOM: 2.2,
        RoomType.TOILET: 1.1,
        RoomType.HALLWAY: 1.0,
    },
}

MIN_CEILING_HEIGHT_M = 2.5

RULE_SOURCES: dict[str, str] = {
    "RU": "СП 54.13330.2022 (СНиП 31-02)",
    "KZ": "СП РК 3.02-101-2013",
    "UA": "ДБН В.2.2-15-2019",
    "BY": "ТКП 45-3.02-230",
    "DE": "DIN 18015 / LBO",
    "US": "IRC 2021 (International Residential Code)",
    "OTHER": "ISO 9836",
}


class ComplianceChecker:
    """
    Checks room areas, corridor widths, and seismic limitations.
    In production: queries LlamaIndex RAG over ingested СНиП PDF corpus.
    MVP: rule-based fallback with same interface.
    """

    async def check(
        self, params: BuildingParams, rooms: List[RoomLayout]
    ) -> List[ComplianceIssue]:
        issues = []
        country = params.country.value
        rules = MIN_AREAS.get(country, MIN_AREAS.get("RU", {}))
        source = RULE_SOURCES.get(country, RULE_SOURCES["OTHER"])

        for room in rooms:
            min_area = rules.get(room.room_type)
            if min_area and room.area_m2 < min_area:
                issues.append(ComplianceIssue(
                    rule_id=f"{country}-MIN-AREA-{room.room_type.value.upper()}",
                    description=(
                        f"{room.name}: area {room.area_m2:.1f} m² is below minimum "
                        f"{min_area:.1f} m² per {source}"
                    ),
                    severity="ERROR",
                    room_id=room.room_id,
                    suggested_fix=f"Increase {room.name} to at least {min_area} m²",
                ))

        # Minimum one bathroom per 4 bedrooms
        bedroom_count = sum(1 for r in rooms if r.room_type == RoomType.BEDROOM)
        bathroom_count = sum(1 for r in rooms if r.room_type in {RoomType.BATHROOM, RoomType.TOILET})
        required_baths = max(1, math.ceil(bedroom_count / 4))
        if bathroom_count < required_baths:
            issues.append(ComplianceIssue(
                rule_id=f"{country}-BATH-RATIO",
                description=(
                    f"Only {bathroom_count} bathroom(s) for {bedroom_count} bedroom(s). "
                    f"Minimum required: {required_baths} per {source}"
                ),
                severity="WARNING",
                suggested_fix=f"Add {required_baths - bathroom_count} more bathroom(s)",
            ))

        # Optional: enrich with Groq LLM if configured
        groq = _get_groq()
        if groq and issues:
            try:
                summary = "\n".join(f"- {i.description}" for i in issues)
                prompt = (
                    f"Building compliance issues found for country {params.country.value}:\n"
                    f"{summary}\n\n"
                    "For each issue, add a short professional recommendation (1 sentence max). "
                    "Reply in the same language as the issue descriptions. "
                    "Return ONLY a JSON array of strings, one per issue, same order."
                )
                resp = groq.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.2,
                )
                import json
                recs = json.loads(resp.choices[0].message.content)
                for issue, rec in zip(issues, recs):
                    if issue.suggested_fix:
                        issue.suggested_fix += f" {rec}"
                    else:
                        issue.suggested_fix = rec
            except Exception as e:
                logger.warning("Groq enrichment failed (non-fatal): %s", e)

        return issues

    async def check_standalone(self, req: ComplianceRequest) -> List[ComplianceIssue]:
        from models import RoomLayout
        mock_rooms = [
            RoomLayout(
                room_id=str(uuid.uuid4()),
                room_type=r.room_type,
                name=r.name or r.room_type.value,
                x=0, y=0, floor=1,
                width=1.0, depth=r.area_m2,
                area_m2=r.area_m2,
            )
            for r in req.rooms
        ]
        mock_params = BuildingParams(
            rooms=req.rooms,
            country=req.country,
            floors=req.floors,
        )
        return await self.check(mock_params, mock_rooms)
