#!/usr/bin/env bash
# scripts/reproduce.sh — Full end-to-end reproduction script for Linux and macOS.
set -euo pipefail

echo "=========================================================================="
echo "RFC RAG CHUNKING LAB — ONE-COMMAND REPRODUCTION (LINUX/MACOS)"
echo "=========================================================================="

# 1. Environment & Prerequisites Check
echo -e "\n[1/5] Checking runtime prerequisites..."
command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || { echo "Python not found in PATH."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js not found in PATH."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm not found in PATH."; exit 1; }

PY_CMD="python3"
if ! command -v python3 >/dev/null 2>&1; then
    PY_CMD="python"
fi

echo "  * Python: $($PY_CMD --version)"
echo "  * Node:   $(node --version)"
echo "  * npm:    $(npm --version)"

# Set Python Path & Thread contention guards
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/backend:$REPO_ROOT"
export OPENBLAS_NUM_THREADS="1"
export OMP_NUM_THREADS="1"

# 2. Run Preprocessing
echo -e "\n[2/5] Running raw RFC cleaning pipeline (datasets/ -> data/clean/)..."
$PY_CMD -m app.cli preprocess

# 3. Validate Questions
echo -e "\n[3/5] Validating 56 evaluation questions and evidence spans..."
$PY_CMD -m app.cli validate-questions

# 4. Run Evaluation Benchmark (Quick Preset: 9 configs)
echo -e "\n[4/5] Executing controlled empirical evaluation (quick preset)..."
$PY_CMD -m app.cli run --preset quick

# 5. Generate Publication Report Assets
echo -e "\n[5/5] Generating publication tables, figures, and methodology description..."
$PY_CMD -m app.cli report-assets --run latest

echo -e "\n=========================================================================="
echo "REPRODUCTION PIPELINE COMPLETE!"
echo "  * Cleaned Corpus:   data/clean/"
echo "  * Benchmark Data:   results/"
echo "  * Report Assets:    report_assets/latest/"
echo "=========================================================================="
