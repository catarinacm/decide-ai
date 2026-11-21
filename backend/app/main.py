"""API do iFood Match (FastAPI)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import ai, groups, metrics, participants, recommendations, reservations, votes
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.errors import install_error_handlers
from app.limiter import limiter
from app.models import tables  # noqa: F401  (registra as tabelas no metadata)
from app.services.match_service import seed_restaurants

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url.startswith("sqlite"):
        # Desenvolvimento local: cria as tabelas e carrega o seed. Em produção, use backend/scripts/migrate.py.
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_restaurants(db)
    yield


app = FastAPI(
    title="iFood Match API",
    version="1.0.0",
    description="Protótipo de case com dados 100% fictícios. Reservas são sempre simuladas.",
    lifespan=lifespan,
)
app.state.limiter = limiter
install_error_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(_, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": {
        "code": "muitas_requisicoes", "message": "Muitas tentativas em pouco tempo. Espere um minuto e tente de novo.",
        "details": str(exc.detail)}})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Participant-Token", "X-Organizer-Token"],
)

for module in (groups, participants, recommendations, votes, reservations, ai, metrics):
    app.include_router(module.router)


@app.get("/health", tags=["infra"])
def health():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degradado", "database": "ok" if db_ok else "erro",
            "ai_enabled": settings.ai_enabled, "model": settings.anthropic_model}
