# Start both backend and frontend dev servers (Windows PowerShell)
# Usage: .\scripts\dev.ps1

$ErrorActionPreference = "Stop"

Write-Host "RFC RAG Chunking Lab — dev server startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Determine repo root (one level up from this script)
$RepoRoot = Split-Path -Parent $PSScriptRoot

# Check for virtual environment
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    Write-Host "Activating virtual environment..." -ForegroundColor Green
    & $VenvActivate
} else {
    Write-Host "Warning: .venv not found. Run: python -m venv .venv" -ForegroundColor Yellow
}

# Run preprocessing if clean files don't exist
$CleanDir = Join-Path $RepoRoot "data\clean"
if (-not (Test-Path (Join-Path $CleanDir "tcp.txt"))) {
    Write-Host "Running preprocessing..." -ForegroundColor Green
    python (Join-Path $RepoRoot "preprocess.py")
}

# Start backend server in a new window
Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Green
$BackendDir = Join-Path $RepoRoot "backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# Wait for backend to start
Start-Sleep -Seconds 2

# Start frontend dev server
Write-Host "Starting Vite frontend on http://localhost:5173 ..." -ForegroundColor Green
$FrontendDir = Join-Path $RepoRoot "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$FrontendDir'; npm run dev"

Write-Host ""
Write-Host "Both servers starting in separate windows." -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
