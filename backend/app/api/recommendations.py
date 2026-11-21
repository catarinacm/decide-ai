"""Gerar e consultar o Match."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.serializers import DIETARY_DISCLAIMER, recommendation_out
from app.database import get_db
from app.limiter import MATCH_LIMIT, limiter
from app.schemas import MatchIn
from app.services import decision_service as ds
from app.services.auth import Caller, group_caller
from app.services.events import log_once
from app.services.match_service import generate_match

router = APIRouter(tags=["match"])


def _ranking(db: Session, caller: Caller) -> dict:
    g = caller.group
    rows = ds.tally(db, g) if g.current_round else []
    return {
        "group_id": str(g.id), "round_number": g.current_round, "status": g.status,
        "summary": g.match_summary,
        "recommendations": [recommendation_out(t["recommendation"], t["votes"], t["voters"]) for t in rows],
        "dietary_disclaimer": DIETARY_DISCLAIMER,
    }


@router.post("/groups/{group_id}/match")
@limiter.limit(MATCH_LIMIT)
def run_match(request: Request, group_id: uuid.UUID, body: MatchIn | None = None,
              caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    body = body or MatchIn()
    actor = caller.participant.id if caller.participant else None
    generate_match(db, caller.group, force=body.force, by_organizer=caller.is_organizer, actor_id=actor)
    db.commit()
    return _ranking(db, caller)


@router.get("/groups/{group_id}/recommendations")
def get_recommendations(group_id: uuid.UUID, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    if ds.maybe_auto_close(db, caller.group):
        db.commit()
    out = _ranking(db, caller)
    if out["recommendations"]:
        pid = caller.participant.id if caller.participant else None
        if log_once(db, "recommendations_viewed", caller.group, pid, round_number=caller.group.current_round):
            db.commit()
    return out
