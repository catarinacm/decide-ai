"""Encontros: criar, consultar, entrar com convite, ajustar e criar a demonstração."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.serializers import group_out
from app.database import get_db
from app.errors import AppError, conflict, not_found
from app.limiter import CREATE_LIMIT, DEMO_LIMIT, JOIN_LIMIT, limiter
from app.models.tables import GroupRow, ParticipantRow
from app.schemas import GroupCreate, GroupUpdate, JoinIn
from app.services import decision_service as ds
from app.services.auth import Caller, group_caller, new_invite_code, new_token
from app.services.demo import create_demo_group
from app.services.events import log_event
from app.services.match_service import invalidate_round, refresh_collect_status
from app.services.state_machine import LABELS, OPEN_STATES

router = APIRouter(tags=["encontros"])
MAX_PARTICIPANTS = 20


def _unique_invite_code(db: Session) -> str:
    for _ in range(10):
        code = new_invite_code()
        if db.scalar(select(GroupRow.id).where(GroupRow.invite_code == code)) is None:
            return code
    raise AppError(500, "erro_interno", "Não foi possível gerar um código de convite.")


def _identity(p: ParticipantRow, raw_token: str) -> dict:
    return {"participant_id": str(p.id), "token": raw_token, "nickname": p.nickname, "is_organizer": p.is_organizer,
            "is_simulated": p.is_simulated}


@router.post("/groups", status_code=201)
@limiter.limit(CREATE_LIMIT)
def create_group(request: Request, body: GroupCreate, db: Session = Depends(get_db)):
    org_raw, org_hash = new_token()
    group = GroupRow(invite_code=_unique_invite_code(db), name=body.name, occasion=body.occasion,
                     event_date=body.event_date, event_time=body.event_time, budget_per_person=body.budget_per_person,
                     party_size=body.party_size, neighborhood=body.neighborhood, city=body.city,
                     vote_deadline=body.vote_deadline, organizer_token_hash=org_hash)
    db.add(group)
    db.flush()
    raw, h = new_token()
    organizer = ParticipantRow(group_id=group.id, nickname=body.organizer_nickname,
                               nickname_key=body.organizer_nickname.lower(), is_organizer=True, token_hash=h)
    group.participants.append(organizer)
    db.flush()
    log_event(db, "group_created", group, organizer.id, party_size=body.party_size, occasion=body.occasion)
    log_event(db, "participant_joined", group, organizer.id, simulated=False)
    db.commit()
    caller = Caller(group, organizer, True)
    return {"group": group_out(db, caller), "organizer_token": org_raw, "identity": _identity(organizer, raw)}


@router.get("/groups/by-code/{invite_code}")
def preview_by_code(invite_code: str, db: Session = Depends(get_db)):
    """Prévia pública do convite (sem dados de participantes)."""
    g = db.scalar(select(GroupRow).where(GroupRow.invite_code == invite_code.strip().upper()))
    if g is None:
        raise not_found("Convite")
    return {"group_id": str(g.id), "name": g.name, "event_date": g.event_date.isoformat(), "event_time": g.event_time,
            "neighborhood": g.neighborhood, "budget_per_person": float(g.budget_per_person), "party_size": g.party_size,
            "joined": len(g.participants), "status": g.status, "status_label": LABELS[g.status],
            "accepting_participants": g.status in OPEN_STATES and len(g.participants) < MAX_PARTICIPANTS,
            "is_demo": g.is_demo}


@router.post("/groups/join", status_code=201)
@limiter.limit(JOIN_LIMIT)
def join_group(request: Request, body: JoinIn, db: Session = Depends(get_db)):
    g = db.scalar(select(GroupRow).where(GroupRow.invite_code == body.invite_code))
    if g is None:
        raise not_found("Convite")
    if g.status not in OPEN_STATES:
        raise conflict("encontro_fechado", "A escolha deste encontro já foi concluída; não dá mais para entrar.")
    if len(g.participants) >= MAX_PARTICIPANTS:
        raise conflict("encontro_lotado", f"Este encontro já tem {MAX_PARTICIPANTS} participantes.")
    key = body.nickname.lower()
    if any(p.nickname_key == key for p in g.participants):
        raise conflict("apelido_em_uso", f"Já tem alguém chamado {body.nickname} neste encontro. Escolha outro apelido.")
    raw, h = new_token()
    p = ParticipantRow(group_id=g.id, nickname=body.nickname, nickname_key=key, token_hash=h,
                       is_simulated=body.is_simulated)
    g.participants.append(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("apelido_em_uso", "Esse apelido acabou de ser usado. Escolha outro.")
    refresh_collect_status(db, g)
    log_event(db, "participant_joined", g, p.id, simulated=body.is_simulated)
    db.commit()
    return {"group_id": str(g.id), "identity": _identity(p, raw)}


@router.get("/groups/{group_id}")
def get_group(group_id: uuid.UUID, caller: Caller = Depends(group_caller), db: Session = Depends(get_db)):
    if ds.maybe_auto_close(db, caller.group):
        db.commit()
    return group_out(db, caller)


@router.patch("/groups/{group_id}")
def update_group(group_id: uuid.UUID, body: GroupUpdate, caller: Caller = Depends(group_caller),
                 db: Session = Depends(get_db)):
    """Ajustes do organizador, por exemplo para aplicar uma sugestão do Match. Abre uma nova rodada."""
    caller.require_organizer()
    g = caller.group
    if g.status not in OPEN_STATES:
        raise conflict("encontro_fechado", "A escolha já foi concluída; o encontro não pode mais ser alterado.")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise AppError(422, "dados_invalidos", "Nada para alterar.")
    for field, value in changes.items():
        setattr(g, field, value)
    db.flush()
    match_changed = set(changes) - {"vote_deadline"}
    if match_changed:
        invalidate_round(db, g, reason="encontro_alterado")
        refresh_collect_status(db, g)
    log_event(db, "group_updated", g, fields=sorted(changes))
    db.commit()
    return group_out(db, caller)


@router.post("/demo", status_code=201)
@limiter.limit(DEMO_LIMIT)
def create_demo(request: Request, db: Session = Depends(get_db)):
    out = create_demo_group(db)
    db.commit()
    g = out["group"]
    organizer = next(p for p in g.participants if p.is_organizer)
    return {"group": group_out(db, Caller(g, organizer, True)), "organizer_token": out["organizer_token"],
            "identities": out["identities"]}
