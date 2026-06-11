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
    from models import BuildingParams
    from core.geo_calculator import GeoClimateCalculator
    from core.layout_engine import LayoutEngine
    from core.ifc_generator import IFCGenerator
    from core.cost_estimator import CostEstimator
    from mep.pipe_router import PipeRouter
    from mep.clash_detector import ClashDetector
    from ai.rag_engine import ComplianceChecker
    import uuid

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

        return {
            "project_id": project_id,
            "status": "completed",
            "ifc_path": ifc_path,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
