"""Função A: texto livre -> preferências estruturadas, para a pessoa conferir antes de salvar."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.limiter import AI_LIMIT, limiter
from app.models.tables import ParticipantRow
from app.schemas import ParseIn
from app.services import ai_service
from app.services.auth import current_participant
from app.services.events import log_event

router = APIRouter(tags=["ia"])


@router.post("/ai/parse-preferences")
@limiter.limit(AI_LIMIT)
def parse_preferences(request: Request, body: ParseIn, participant: ParticipantRow = Depends(current_participant),
                      db: Session = Depends(get_db)):
    result = ai_service.parse_preferences(body.text)
    log_event(db, "ai_call", participant.group, participant.id, function="interpretacao", source=result.source,
              error=result.error, latency_ms=result.latency_ms, model=settings.anthropic_model)
    db.commit()
    return {
        "preferences": result.data.model_dump(),
        "source": result.source,
        "message": ("Preenchemos o formulário com o que entendemos. Confira e corrija antes de salvar."
                    if result.source == "ia" else
                    "A IA não respondeu a tempo; preenchemos por palavras-chave. Confira antes de salvar."),
    }
