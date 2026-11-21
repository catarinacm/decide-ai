"""Votação: um voto ativo por participante por rodada, placar e encerramento."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import recommendation_out
from app.database import get_db
from app.schemas import VoteIn
from app.services import decision_service as ds
from app.services.auth import Caller, group_caller

router = APIRouter(tags=["votacao"])


def _results(db: Session, caller: Caller) -> dict:
    g = caller.group
    rows = ds.tally(db, g) if g.current_round else []
    me = caller.participant
    my_vote = None
    if me is not None:
        my_vote = next((str(v.recommendation_id) for v in ds.round_votes(db, g) if v.participant_id == me.id), None)
    winner_id = str(g.winner_recommendation_id) if g.winner_recommendation_id else None
    leader = ds.pick_winner(rows)[0]["recommendation"] if rows else None
    return {
        "group_id": str(g.id), "round_number": g.current_round, "status": g.status,
        "total_votes": sum(t["votes"] for t in rows), "participants": len(g.participants),
        "pending_voters": [p.nickname for p in g.participants
                           if p.id not in {v.participant_id for v in ds.round_votes(db, g)}] if rows else [],
        "options": [recommendation_out(t["recommendation"], t["votes"], t["voters"]) for t in rows],
        "my_vote": my_vote,
        "current_leader_id": str(leader.id) if leader else None,
        "winner_recommendation_id": winner_id,
        "decision_note": g.decision_note,
        "vote_deadline": g.vote_deadline.isoformat() if g.vote_deadline else None,
        "tie_rule": "Em caso de empate, vence a opção com maior score coletivo.",
    }


@router.post("/groups/{group_id}/votes")
def vote(group_id: uuid.UUID, body: VoteIn, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    participant = caller.require_participant()
    ds.cast_vote(db, caller.group, participant, body.recommendation_id)
    db.commit()
    return _results(db, caller)


@router.get("/groups/{group_id}/results")
def results(group_id: uuid.UUID, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    if ds.maybe_auto_close(db, caller.group):
        db.commit()
    return _results(db, caller)


@router.post("/groups/{group_id}/close-voting")
def close(group_id: uuid.UUID, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    caller.require_organizer()
    winner = ds.close_voting(db, caller.group, reason="organizador")
    db.commit()
    out = _results(db, caller)
    out["winner"] = recommendation_out(winner)
    return out
