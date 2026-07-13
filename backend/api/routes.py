import json
import logging
import math
import os
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from ai.rag_engine import ComplianceChecker
from config import settings
from core.cost_estimator import CostEstimator
from core.geo_calculator import GeoClimateCalculator
from core.heat_calculator import estimate_heating
from core.ifc_generator import IFCGenerator
from core.insolation import annotate as annotate_insolation
from core.insolation import score as insolation_score
from core.llm_layout_engine import LLMLayoutEngine
from core.orientation import best_turns, rotate_layout
from core.plan_invariants import check_invariants
from core.ratelimit import limiter
from core.site_planner import check_site, plan_site
from core.variants import build_variants
from mep.clash_detector import ClashDetector
from mep.pipe_router import PipeRouter
from models import (
    BuildingParams,
    ComplianceIssue,
    ComplianceRequest,
    CountryCode,
    GenerationResult,
    MEPConflict,
    MEPRoutingRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

geo_calc = GeoClimateCalculator()
rag_checker = ComplianceChecker()

# project_id is always a uuid4 we generated; rejecting anything else closes
# the path-traversal door on every file-serving endpoint below.
UUID_PATH = Path(
    pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Anonymous device identity (no accounts in the MVP): the frontend mints a
# uuid per browser and sends it as X-Device-Token; we stamp it into the stored
# result so /projects can list only that device's history. Junk tokens are
# treated as absent rather than rejected.
_TOKEN_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def _norm_token(token: str | None) -> str | None:
    return token if token and _TOKEN_RE.match(token) else None


@router.post("/generate-plan", response_model=GenerationResult)
async def generate_plan(
    params: BuildingParams,
    request: Request,
    x_device_token: str | None = Header(default=None),
):
    """
    Main endpoint: accepts building parameters, returns full IFC + analysis.
    """
    # Abuse guard: generation spends paid Groq tokens. Keyed by client IP
    # (device tokens are client-minted, so they can't be the limiter key).
    # Behind nginx this needs uvicorn --proxy-headers to see the real IP.
    client_ip = request.client.host if request.client else "unknown"
    retry_after = limiter.check(
        client_ip,
        [
            (settings.RATE_LIMIT_PER_MINUTE, 60),
            (settings.RATE_LIMIT_PER_DAY, 86400),
        ],
    )
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded — try again later",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )

    project_id = str(uuid.uuid4())

    # 1. Geoclimate calculation. Resolve the region globally first: a real place
    # keeps its own seismicity/frost regardless of the picked country, and the
    # matched region's country becomes the effective country for currency.
    region_res = geo_calc.resolve(params.country, params.region)
    geo_data = geo_calc.calculate(params.country, params.region, params.floors)
    effective_country = CountryCode(region_res.effective_country)

    # 2. Validate floors vs seismic limit
    warnings = []
    if params.floors > geo_data.max_floors_seismic:
        warnings.append(
            f"Seismic zone {geo_data.seismic_zone} limits building to "
            f"{geo_data.max_floors_seismic} floors. Requested: {params.floors}"
        )
    # An unrecognized region must flag, not silently borrow country averages
    # under the city's name — the same honesty rule as the rest of the product.
    if params.region and not region_res.recognized:
        warnings.append(
            f"Регион «{params.region}» не распознан — использованы средние параметры "
            f"страны. Уточните сейсмичность и глубину промерзания участка у специалиста."
        )

    # 3. Generate 2D/3D layout
    layout_engine = LLMLayoutEngine(params, geo_data)
    rooms = layout_engine.generate()
    warnings.extend(layout_engine.warnings)

    # 3a. Orientation actuator (optional) — hard-rotate the finished plan to the
    # quarter-turn that best faces rooms to the sun, then reassign openings.
    if params.auto_orient:
        turns = best_turns(rooms, params.facing, params.plot_width_m, params.plot_depth_m)
        if turns:
            rotate_layout(rooms, turns)

    # 3b. Daylight sensor — annotate each room's sun rating for the given facing.
    annotate_insolation(rooms, params.facing)

    # 4. MEP routing and clash detection
    pipe_router = PipeRouter(rooms, params.floors, geo_data)
    pipes = pipe_router.route()
    clash_detector = ClashDetector(rooms, pipes)
    conflicts = clash_detector.detect()

    # 5. Compliance check via RAG + the 9 deterministic invariants. The
    # invariant checker used to run only in tests, so a plan violating rule 9
    # (a 1.8 m "living room") shipped with a green "all rules passed" badge.
    # Violations are ERRORs with the message text intact — the user must read
    # WHAT is broken, not just see a lower score. Runs after auto-orient so it
    # judges the final geometry.
    compliance_issues = [
        ComplianceIssue(
            rule_id=f"INV-{v.rule}-{v.code.upper()}",
            description=v.message,
            severity=v.severity,
            room_id=v.room_id,
        )
        for v in check_invariants(rooms, openness=params.openness)
    ]
    compliance_issues.extend(await rag_checker.check(params, rooms))

    # 5a. Site placement — put the building on its plot and mirror any setback
    # or coverage breach into compliance_issues as a red SITE-* ERROR (same
    # honesty contract as the invariants). Only when a full plot size is given;
    # the tool still works with no plot. Runs after auto-orient so the placed
    # footprint matches the final geometry.
    site = None
    if params.plot_width_m and params.plot_depth_m:
        site = plan_site(
            rooms,
            params.plot_width_m,
            params.plot_depth_m,
            params.street_side,
            geo_data.seismic_zone,
        )
        compliance_issues.extend(
            ComplianceIssue(
                rule_id=f"SITE-{v.rule}-{v.code}",
                description=v.message,
                severity="ERROR",
            )
            for v in check_site(site)
        )

    # 6. Generate IFC file
    ifc_gen = IFCGenerator(project_id, params, rooms, pipes, geo_data)
    ifc_gen.generate()
    ifc_url = f"/api/v1/download/{project_id}"

    # 7. Cost estimation — currency follows the effective (region-matched)
    # country, so typing "Алматы" prices in ₸ without picking KZ for it.
    estimator = CostEstimator(rooms, geo_data, effective_country)
    cost = estimator.estimate()

    # 7a. Cost-Δ decision table: the same program at three deterministic
    # spaciousness settings, sorted by cost — the honest "what does roomier
    # actually cost" comparison next to the hero figure.
    variants = build_variants(params, geo_data, effective_country)

    result = GenerationResult(
        project_id=project_id,
        rooms=rooms,
        geo_climate=geo_data,
        mep_conflicts=conflicts,
        compliance_issues=compliance_issues,
        cost_estimate=cost,
        ifc_file_url=ifc_url,
        warnings=warnings,
        insolation_score=insolation_score(rooms, params.facing),
        site=site,
        region_recognized=region_res.recognized,
        variants=variants,
        heating=estimate_heating(rooms, geo_data),
    )

    # Persist the result next to the IFC so /report/{id} and project history
    # can re-read it without a database. The owner token rides inside the same
    # JSON as an extra field: pydantic ignores it on load, so /projects/{id}
    # never echoes it back.
    try:
        data = json.loads(result.model_dump_json())
        owner = _norm_token(x_device_token)
        if owner:
            data["_owner"] = owner
        result_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError as exc:
        # Fail honestly: a "successful" response whose report/share/history
        # 404s later is worse than asking the user to regenerate.
        logger.error("Could not persist result for %s: %s", project_id, exc)
        raise HTTPException(
            status_code=500,
            detail="The plan was generated but could not be saved — please try again",
        ) from exc

    return result


@router.post("/compliance-check", response_model=list[ComplianceIssue])
async def compliance_check(req: ComplianceRequest):
    """
    Standalone compliance check against building codes (СНиП/SP) via RAG.
    """
    issues = await rag_checker.check_standalone(req)
    return issues


@router.post("/mep-routing", response_model=list[MEPConflict])
async def mep_routing(req: MEPRoutingRequest):
    """
    Re-run MEP pipe routing and clash detection for existing layout.
    """
    pipe_router = PipeRouter(req.rooms, req.floors, None)
    pipes = pipe_router.route()
    clash_detector = ClashDetector(req.rooms, pipes)
    conflicts = clash_detector.detect()
    return conflicts


@router.get("/download/{project_id}")
async def download_ifc(project_id: str = UUID_PATH):
    ifc_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.ifc")
    if not os.path.exists(ifc_path):
        raise HTTPException(status_code=404, detail="IFC file not found")
    return FileResponse(
        ifc_path,
        media_type="application/octet-stream",
        filename=f"archvision_{project_id}.ifc",
    )


def _load_result(project_id: str) -> GenerationResult:
    """Load a persisted GenerationResult or raise the right HTTP error."""
    result_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.json")
    if not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        with open(result_path, encoding="utf-8") as f:
            return GenerationResult.model_validate_json(f.read())
    except ValidationError:
        # File was written by an older schema version — regeneration required.
        raise HTTPException(
            status_code=410,
            detail="Stored project data is incompatible with the current version; regenerate the plan",
        ) from None


@router.get("/projects")
async def list_projects(
    limit: int = Query(20, ge=1, le=100),
    x_device_token: str | None = Header(default=None),
):
    """This device's recent projects (newest first) — backs the history UI.

    Without a device token the list is empty: projects are private to the
    device that generated them; sharing is by explicit /projects/{id} link.
    """
    owner = _norm_token(x_device_token)
    if owner is None:
        return []
    try:
        files = [f for f in os.listdir(settings.IFC_OUTPUT_DIR) if f.endswith(".json")]
    except OSError:
        return []

    def mtime(name: str) -> float:
        try:
            return os.path.getmtime(os.path.join(settings.IFC_OUTPUT_DIR, name))
        except OSError:
            return 0.0

    files.sort(key=mtime, reverse=True)
    entries = []
    for fname in files:
        if len(entries) >= limit:
            break
        path = os.path.join(settings.IFC_OUTPUT_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if json.loads(text).get("_owner") != owner:
                continue
            result = GenerationResult.model_validate_json(text)
        except (OSError, ValueError, ValidationError):
            continue  # skip unreadable/foreign/outdated entries rather than failing
        entries.append(
            {
                "project_id": fname[:-5],
                "created_at": datetime.fromtimestamp(mtime(fname), tz=UTC).isoformat(),
                "rooms": len(result.rooms),
                "floors": max((r.floor for r in result.rooms), default=1),
                # Actual tiled footprint (w×d) — the same single definition the
                # canvas, штамп and PDF show; area_m2 is the REQUEST, not the plan.
                "total_area_m2": round(sum(r.width * r.depth for r in result.rooms), 1),
                "country_currency": result.cost_estimate.currency,
            }
        )
    return entries


@router.get("/projects/{project_id}", response_model=GenerationResult)
async def get_project(project_id: str = UUID_PATH):
    """Full stored result — used by share-by-link on the frontend."""
    return _load_result(project_id)


@router.get("/report/{project_id}")
async def pdf_report(
    project_id: str = UUID_PATH,
    lang: str = Query("en", pattern="^(en|ru|kk)$"),
):
    """Localized PDF report for a previously generated project."""
    from core.pdf_generator import generate_pdf

    result = _load_result(project_id)
    pdf_bytes = generate_pdf(result, lang)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="archvision_{project_id[:8]}.pdf"'},
    )


@router.get("/countries")
async def list_countries():
    return geo_calc.supported_countries()
