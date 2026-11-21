"""Reserva simulada e avaliação (retorno)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import reservation_out
from app.database import get_db
from app.errors import not_found
from app.models.tables import ParticipantRow, ReservationRow
from app.schemas import ReviewIn
from app.services import decision_service as ds
from app.services.auth import Caller, current_participant, group_caller

router = APIRouter(tags=["reserva"])


@router.post("/groups/{group_id}/reservations", status_code=201)
def reserve(group_id: uuid.UUID, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    caller.require_organizer()
    res = ds.create_reservation(db, caller.group)
    db.commit()
    return reservation_out(db, res, caller.participant.id if caller.participant else None)


@router.post("/reservations/{reservation_id}/reviews", status_code=201)
def review(reservation_id: uuid.UUID, body: ReviewIn, participant: ParticipantRow = Depends(current_participant),
           db: Session = Depends(get_db)):
    res = db.get(ReservationRow, reservation_id)
    if res is None:
        raise not_found("Reserva")
    ds.add_review(db, res, participant, body.rating, body.comment)
    db.commit()
    return reservation_out(db, res, participant.id)
