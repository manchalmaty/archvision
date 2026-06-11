from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from api.routes import router
from config import settings

app = FastAPI(
    title="ArchVision AI",
    description="AI-powered architectural draft generation for residential buildings",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.IFC_OUTPUT_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.IFC_OUTPUT_DIR), name="files")

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "archvision-backend"}
