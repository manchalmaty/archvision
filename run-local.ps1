# ArchVision AI — Local development startup (no Docker required)
# Run from project root: .\run-local.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== ArchVision AI — Local Dev ===" -ForegroundColor Cyan

# Check Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Node.js not found. Install from https://nodejs.org" -ForegroundColor Red
    exit 1
}

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

Write-Host "[1/4] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location frontend
npm install
Pop-Location

Write-Host "[2/4] Creating backend virtualenv..." -ForegroundColor Yellow
Push-Location backend

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Activate venv
& .\.venv\Scripts\Activate.ps1

Write-Host "[3/4] Installing backend dependencies (no ifcopenshell)..." -ForegroundColor Yellow
pip install -r requirements-local.txt

# Copy .env.local to .env if .env doesn't exist
if (-not (Test-Path ".env")) {
    Copy-Item ".env.local" ".env"
    Write-Host "Created .env from .env.local" -ForegroundColor Green
}

# Create output dir
New-Item -ItemType Directory -Force -Path "generated" | Out-Null

Pop-Location

Write-Host "[4/4] Starting services..." -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTE: Backend needs PostgreSQL and Redis running locally." -ForegroundColor DarkYellow
Write-Host "      Quick option: run only these Docker services:" -ForegroundColor DarkYellow
Write-Host "      docker compose up postgres redis -d" -ForegroundColor White
Write-Host ""

# Start frontend in background
$frontendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD\frontend
    npm run dev
}

# Start backend
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$PWD\backend'; .\.venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000"
) -WindowStyle Normal

Write-Host ""
Write-Host "=== Services starting ===" -ForegroundColor Green
Write-Host "Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor DarkGray
