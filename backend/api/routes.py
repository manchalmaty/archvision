import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from ai.rag_engine import ComplianceChecker
from config import settings
from core.cost_estimator import CostEstimator
from core.geo_calculator import GeoClimateCalculator
from core.ifc_generator import IFCGenerator
from core.insolation import annotate as annotate_insolation
from core.insolation import score as insolation_score
from core.llm_layout_engine import LLMLayoutEngine
from core.orientation import best_turns, rotate_layout
from mep.clash_detector import ClashDetector
from mep.pipe_router import PipeRouter
from models import (
    BuildingParams,
    ComplianceIssue,
    ComplianceRequest,
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


@router.post("/generate-plan", response_model=GenerationResult)
async def generate_plan(params: BuildingParams):
    """
    Main endpoint: accepts building parameters, returns full IFC + analysis.
    """
    project_id = str(uuid.uuid4())

    # 1. Geoclimate calculation
    geo_data = geo_calc.calculate(params.country, params.region, params.floors)

    # 2. Validate floors vs seismic limit
    warnings = []
    if params.floors > geo_data.max_floors_seismic:
        warnings.append(
            f"Seismic zone {geo_data.seismic_zone} limits building to "
            f"{geo_data.max_floors_seismic} floors. Requested: {params.floors}"
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

    # 5. Compliance check via RAG
    compliance_issues = await rag_checker.check(params, rooms)

    # 6. Generate IFC file
    ifc_gen = IFCGenerator(project_id, params, rooms, pipes, geo_data)
    ifc_path = ifc_gen.generate()
    ifc_url = f"/files/{os.path.basename(ifc_path)}"

    # 7. Cost estimation
    estimator = CostEstimator(rooms, geo_data, params.country)
    cost = estimator.estimate()

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
    )

    # Persist the result next to the IFC so /report/{id} (and later project
    # history) can re-read it without a database.
    try:
        result_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json())
    except OSError as exc:
        # Non-fatal (generation succeeded), but /report/{id} will 404 —
        # leave a trail so operators can correlate.
        logger.warning("Could not persist result for %s: %s", project_id, exc)

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
async def list_projects(limit: int = Query(20, ge=1, le=100)):
    """Recent projects (newest first) — backs the history UI and share links."""
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
    for fname in files[:limit]:
        project_id = fname[:-5]
        try:
            result = _load_result(project_id)
        except HTTPException:
            continue  # skip unreadable/outdated entries rather than failing the list
        entries.append(
            {
                "project_id": project_id,
                "created_at": datetime.fromtimestamp(mtime(fname), tz=UTC).isoformat(),
                "rooms": len(result.rooms),
                "floors": max((r.floor for r in result.rooms), default=1),
                "total_area_m2": round(sum(r.area_m2 for r in result.rooms), 1),
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
