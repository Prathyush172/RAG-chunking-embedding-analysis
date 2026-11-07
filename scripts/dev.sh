#!/usr/bin/env bash
# Start both backend and frontend dev servers (macOS / Linux bash)
# Usage: bash scripts/dev.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "RFC RAG Chunking Lab — dev server startup"
echo "=========================================="

# Activate virtual environment if present
if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$REPO_ROOT/.venv/bin/activate"
else
    echo "Warning: .venv not found. Run: python3.11 -m venv .venv && pip install -r requirements.txt"
fi

# Run preprocessing if clean files don't exist
CLEAN_DIR="$REPO_ROOT/data/clean"
if [ ! -f "$CLEAN_DIR/tcp.txt" ]; then
    echo "Running preprocessing..."
    python "$REPO_ROOT/preprocess.py"
fi

# Start backend server in background
echo "Starting FastAPI backend on http://localhost:8000 ..."
cd "$REPO_ROOT/backend"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to start
sleep 2

# Start frontend dev server in background
echo "Starting Vite frontend on http://localhost:5173 ..."
cd "$REPO_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "Both servers are running."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait and handle SIGINT to kill both processes
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
