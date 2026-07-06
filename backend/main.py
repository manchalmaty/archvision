import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config import settings
from core.storage import cleanup_expired_results

# Structured-ish logging: timestamp, level, logger, message. Uvicorn keeps its
# own access log; this covers app loggers (routes, pdf_generator, ...).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def _ttl_loop() -> None:
    while True:
        cleanup_expired_results(settings.IFC_OUTPUT_DIR, settings.RESULT_TTL_DAYS)
        await asyncio.sleep(86400)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_ttl_loop())
    yield
    task.cancel()


app = FastAPI(
    title="ArchVision AI",
    description="AI-powered architectural draft generation for residential buildings",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# No static mount over IFC_OUTPUT_DIR: it would serve the raw {id}.json files
# including the private _owner device token. Files go out only through the
# validated API endpoints (/download strips nothing, /projects/{id} re-parses
# through the model, which drops _owner).
os.makedirs(settings.IFC_OUTPUT_DIR, exist_ok=True)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Deep-enough health for a container check: process up + store writable."""
    probe = os.path.join(settings.IFC_OUTPUT_DIR, ".health_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        storage = "ok"
    except OSError:
        storage = "unwritable"
    status = "ok" if storage == "ok" else "degraded"
    return {
        "status": status,
        "service": "archvision-backend",
        "storage": storage,
        "llm": "groq" if settings.GROQ_API_KEY else "rule-engine-fallback",
    }
