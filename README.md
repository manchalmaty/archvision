# ArchVision AI

AI-powered architectural draft generator for residential buildings.
Generates IFC/BIM models with geoclimate analysis, MEP routing, and compliance checking.

## Quick Start

### Prerequisites
- Docker Desktop
- 8GB RAM minimum (16GB recommended for Ollama)

### Run

```bash
docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Ollama: http://localhost:11434

### Pull LLM model (first run)

```bash
docker exec -it $(docker compose ps -q ollama) ollama pull llama3
docker exec -it $(docker compose ps -q ollama) ollama pull nomic-embed-text
```

## Architecture

```
User Input → FastAPI → GeoClimate Calc (NumPy)
                     → Layout Engine (greedy strip packing)
                     → IFC Generator (IfcOpenShell)
                     → MEP Router (3D A*)
                     → Clash Detector
                     → RAG Compliance (LlamaIndex + pgvector)
                     → Cost Estimator
           → React Three Fiber (3D viewer)
           → Results Panel (costs, compliance, MEP clashes)
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/generate-plan` | Full generation: IFC + analysis |
| POST | `/api/v1/compliance-check` | Building code check only |
| POST | `/api/v1/mep-routing` | MEP routing + clash detection |
| GET | `/api/v1/download/{id}` | Download IFC file |
| GET | `/api/v1/countries` | Supported countries + regions |

## Disclaimer

> Schematic design for preliminary assessment only.
> Requires certification by a licensed architect before use in construction.
