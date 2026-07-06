# ArchVision AI

AI-powered architectural draft generator for residential buildings (RU/KZ/CIS).
Household → 2D floor plan, plumbing draft, cost estimate, localized PDF report, IFC export.

## Quick Start (development)

### Prerequisites
- Docker Desktop (or Python 3.11 + Node 20 locally)
- Optional: a [Groq](https://console.groq.com) API key — without it the
  deterministic rule engine does the layout (fully offline)

### Run

```bash
cp backend/.env.example backend/.env   # put your GROQ_API_KEY here (optional)
docker compose up --build
```

Services:
- Frontend (Vite dev): http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Local without Docker (Windows): `run-local.ps1`, or manually —
`backend\.venv\Scripts\uvicorn main:app --reload --port 8000` (from `backend/`)
and `npm run dev` (from `frontend/`).

## Production

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

nginx serves the built SPA on :80 and proxies `/api` to uvicorn; generated
projects persist in the `ifc_files` volume (TTL-cleaned after
`RESULT_TTL_DAYS`, default 30). `/generate-plan` is rate-limited per client IP
(`RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_PER_DAY`). Terminate TLS on the host
(nginx/caddy + certbot) and point it at the frontend container.

## Architecture

```
User Input → FastAPI → GeoClimate Calc (NumPy)
                     → Layout Engine (central-hall tiling; Groq agentic loop
                       with deterministic validator + rule-engine fallback)
                     → Daylight sensor/auto-orientation
                     → MEP draft (riser + branches) + clash advisories
                     → Compliance rules (СНиП/SP-derived checks)
                     → Cost Estimator (strip foundation model)
                     → IFC Generator (IfcOpenShell) · PDF (reportlab, en/ru/kk)
           → React + SVG 2D plan (three.js 3D viewer lazy-loaded)
           → Results panel (cost hero, geoclimate, compliance, MEP)
```

No accounts: an anonymous per-browser device token scopes project history;
plans are shared by unguessable link (`#/p/{id}`).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/generate-plan` | Full generation: plan + analysis + IFC (rate-limited) |
| POST | `/api/v1/compliance-check` | Building code check only |
| POST | `/api/v1/mep-routing` | MEP routing + clash detection |
| GET | `/api/v1/projects` | This device's history (X-Device-Token header) |
| GET | `/api/v1/projects/{id}` | Full stored result (share-by-link) |
| GET | `/api/v1/download/{id}` | Download IFC file |
| GET | `/api/v1/report/{id}?lang=en\|ru\|kk` | Localized PDF report |
| GET | `/api/v1/countries` | Supported countries + regions |
| GET | `/health` | Liveness + storage writability |

## Tests & gates

```bash
cd backend && pytest -q && ruff check . && black --check .
cd frontend && npx vitest run && npx tsc --noEmit && npm run lint && npm run format:check
```

## Disclaimer

> Schematic design for preliminary assessment only.
> Requires certification by a licensed architect before use in construction.
