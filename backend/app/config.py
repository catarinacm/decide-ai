"""Configuração lida do ambiente (.env local ou painel do Render). Nenhum segredo no código."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "sim"}


def normalize_db_url(url: str) -> str:
    """Aceita a connection string do Supabase como ela vem do painel e usa o driver psycopg 3."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    def __init__(self) -> None:
        raw_db = os.getenv("DATABASE_URL", "").strip()
        self.database_url = normalize_db_url(raw_db) if raw_db else "sqlite:///./decide_ai.db"
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()
        self.ai_timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "8"))
        self.ai_enabled = _bool("AI_ENABLED", True) and bool(self.anthropic_api_key)
        self.cors_origins = [o.strip() for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
        # Domínio de produção na Vercel e as URLs de preview só desta conta (decide-<hash>-catarinacm.vercel.app).
        self.cors_origin_regex = os.getenv(
            "CORS_ORIGIN_REGEX", r"https://(decide-ai-pi|decide-[a-z0-9-]+-catarinacm)\.vercel\.app")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
        self.rate_limit_enabled = _bool("RATE_LIMIT_ENABLED", True)
        # Chave privada da dona do produto para ver as métricas. Sem ela, /metrics fica fechado.
        self.admin_token = os.getenv("ADMIN_TOKEN", "").strip()


settings = Settings()
