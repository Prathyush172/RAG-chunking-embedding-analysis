# scripts/reproduce.ps1 — Full end-to-end reproduction script for Windows 11 PowerShell.
$ErrorActionPreference = "Stop"

Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host "RFC RAG CHUNKING LAB — ONE-COMMAND REPRODUCTION (WINDOWS)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

# 1. Environment & Prerequisites Check
Write-Host "`n[1/5] Checking runtime prerequisites..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
$pip = Get-Command pip -ErrorAction SilentlyContinue
$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue

if (-not $py) { Write-Error "Python not found in PATH." }
if (-not $node) { Write-Error "Node.js not found in PATH." }
if (-not $npm) { Write-Error "npm not found in PATH." }

Write-Host "  * Python: $(python --version)" -ForegroundColor Green
Write-Host "  * Node:   $(node --version)" -ForegroundColor Green
Write-Host "  * npm:    $(npm --version)" -ForegroundColor Green

# Set Python Path & Thread contention guards
$env:PYTHONPATH = "$PSScriptRoot\..\backend;$PSScriptRoot\.."
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"

# 2. Run Preprocessing
Write-Host "`n[2/5] Running raw RFC cleaning pipeline (datasets/ -> data/clean/)..." -ForegroundColor Yellow
python -m app.cli preprocess

# 3. Validate Questions
Write-Host "`n[3/5] Validating 56 evaluation questions and evidence spans..." -ForegroundColor Yellow
python -m app.cli validate-questions

# 4. Run Evaluation Benchmark (Quick Preset: 9 configs)
Write-Host "`n[4/5] Executing controlled empirical evaluation (quick preset)..." -ForegroundColor Yellow
python -m app.cli run --preset quick

# 5. Generate Publication Report Assets
Write-Host "`n[5/5] Generating publication tables, figures, and methodology description..." -ForegroundColor Yellow
python -m app.cli report-assets --run latest

Write-Host "`n==========================================================================" -ForegroundColor Green
Write-Host "REPRODUCTION PIPELINE COMPLETE!" -ForegroundColor Green
Write-Host "  * Cleaned Corpus:   data/clean/" -ForegroundColor Green
Write-Host "  * Benchmark Data:   results/" -ForegroundColor Green
Write-Host "  * Report Assets:    report_assets/latest/" -ForegroundColor Green
Write-Host "==========================================================================" -ForegroundColor Green
