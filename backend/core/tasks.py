"""
Celery async tasks for long-running generation jobs.
"""

from core.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2)
def generate_plan_async(self, params_dict: dict) -> dict:
    """
    Background task for large buildings or high floor counts.
    Mirrors the sync generate-plan endpoint but runs in worker.
    """
    import asyncio
    import os
    import uuid

    from ai.rag_engine import ComplianceChecker
    from config import settings
    from core.cost_estimator import CostEstimator
    from core.geo_calculator import GeoClimateCalculator
    from core.ifc_generator import IFCGenerator
    from core.layout_engine import LayoutEngine
    from mep.clash_detector import ClashDetector
    from mep.pipe_router import PipeRouter
    from models import BuildingParams, GenerationResult

    try:
        params = BuildingParams(**params_dict)
        project_id = str(uuid.uuid4())
        geo_calc = GeoClimateCalculator()
        geo_data = geo_calc.calculate(params.country, params.region, params.floors)
        layout_engine = LayoutEngine(params, geo_data)
        rooms = layout_engine.generate()
        pipe_router = PipeRouter(rooms, params.floors, geo_data)
        pipes = pipe_router.route()
        clash_detector = ClashDetector(rooms, pipes)
        conflicts = clash_detector.detect()
        rag_checker = ComplianceChecker()
        compliance_issues = asyncio.get_event_loop().run_until_complete(
            rag_checker.check(params, rooms)
        )
        ifc_gen = IFCGenerator(project_id, params, rooms, pipes, geo_data)
        ifc_path = ifc_gen.generate()
        estimator = CostEstimator(rooms, geo_data, params.country)
        cost = estimator.estimate()

        result = GenerationResult(
            project_id=project_id,
            rooms=rooms,
            geo_climate=geo_data,
            mep_conflicts=conflicts,
            compliance_issues=compliance_issues,
            cost_estimate=cost,
            ifc_file_url=f"/files/{os.path.basename(ifc_path)}",
            warnings=layout_engine.warnings,
        )

        # Persist alongside the IFC so the project-history endpoints can re-read
        # it without a database, mirroring the sync generate-plan path.
        result_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{project_id}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json())

        return {
            "project_id": project_id,
            "status": "completed",
            "ifc_path": ifc_path,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc
