import hashlib
import json
import logging
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    compare,
    configs,
    corpus,
    decision_matrix,
    experiments,
    export,
    playground,
    questions,
    results,
    settings,
)
from app.core.index import FaissIndexManager
from app.core.jobs import QUESTIONS_FILE, CLEAN_DIR
from app.db.session import SessionLocal, init_db
from app.db.sync import sync_disk_results_to_db
from app.schemas import ErrorEnvelope, ErrorDetail, HealthResponse

logger = logging.getLogger("app.main")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

CONTRACT_DIR = Path("frontend-contract")


def compute_corpus_hash() -> str:
    hasher = hashlib.sha256()
    if CLEAN_DIR.exists():
        for p in sorted(CLEAN_DIR.glob("*.txt")):
            hasher.update(p.read_bytes())
    return hasher.hexdigest()[:16]


def compute_questions_hash() -> str:
    hasher = hashlib.sha256()
    if QUESTIONS_FILE.exists():
        hasher.update(QUESTIONS_FILE.read_bytes())
    return hasher.hexdigest()[:16]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        logger.info("Syncing historical disk runs to SQLite...")
        sync_disk_results_to_db(db)
    finally:
        db.close()

    # Generate frontend contract OpenAPI JSON
    try:
        CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
        openapi_data = app.openapi()
        with open(CONTRACT_DIR / "openapi.json", "w", encoding="utf-8") as f:
            json.dump(openapi_data, f, indent=2)
        logger.info("Generated frontend OpenAPI contract at %s", CONTRACT_DIR / "openapi.json")
    except Exception as e:
        logger.warning("Could not export OpenAPI contract: %s", e)

    yield

    # Shutdown
    logger.info("Shutting down application...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RFC RAG Chunking Lab API",
        version="1.0.0",
        description="REST backend for comparative empirical analysis of chunking strategies and embedding models on technical RFC documentation.",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error Handlers to wrap in standard ErrorEnvelope
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code=f"HTTP_{exc.status_code}",
                    message=str(exc.detail),
                )
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details=exc.errors(),
                )
            ).model_dump(),
        )

    # Health Check
    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def get_health() -> HealthResponse:
        idx_mgr = FaissIndexManager()
        cached = idx_mgr.list_cached_configs()
        return HealthResponse(
            status="ok",
            device="cpu",
            faiss_threads=1,
            python_version=platform.python_version(),
            corpus_hash=compute_corpus_hash(),
            questions_hash=compute_questions_hash(),
            indexed_configs=cached,
        )

    # Include Routers
    app.include_router(corpus.router, prefix="/api")
    app.include_router(questions.router, prefix="/api")
    app.include_router(configs.router, prefix="/api")
    app.include_router(experiments.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    app.include_router(compare.router, prefix="/api")
    app.include_router(playground.router, prefix="/api")
    app.include_router(decision_matrix.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    return app


app = create_app()
