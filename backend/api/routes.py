from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import uuid
import os

from models import (
    BuildingParams, GenerationResult, ComplianceRequest,
    MEPRoutingRequest, ComplianceIssue, MEPConflict
)
from core.ifc_generator import IFCGenerator
from core.geo_calculator import GeoClimateCalculator
from core.cost_estimator import CostEstimator
from core.layout_engine import LayoutEngine
from mep.pipe_router import PipeRouter
from mep.clash_detector import ClashDetector
from ai.rag_engine import ComplianceChecker
from config import settings

router = APIRouter()

geo_calc = GeoClimateCalculator()
rag_checker = ComplianceChecker()


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
    layout_engine = LayoutEngine(params, geo_data)
    rooms = layout_engine.generate()

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

    return GenerationResult(
        project_id=project_id,
        rooms=rooms,
        geo_climate=geo_data,
        mep_conflicts=conflicts,
        compliance_issues=compliance_issues,
        cost_estimate=cost,
        ifc_file_url=ifc_url,
        warnings=warnings,
    )


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
async def download_ifc(project_id: str):
    ifc_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.ifc")
    if not os.path.exists(ifc_path):
        raise HTTPException(status_code=404, detail="IFC file not found")
    return FileResponse(
        ifc_path,
        media_type="application/octet-stream",
        filename=f"archvision_{project_id}.ifc",
    )


@router.get("/countries")
async def list_countries():
    return geo_calc.supported_countries()
