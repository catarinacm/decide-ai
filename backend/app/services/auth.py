"""Convites e credenciais.

- Código de convite: 8 caracteres aleatórios de `secrets`, sem letras ambíguas (31^8 ≈ 8,5 × 10^11 combinações).
- Cada participante recebe um token de sessão (guardado no localStorage do navegador); o banco guarda só o hash.
- O organizador recebe um token separado para ações de grupo (gerar com quem respondeu, encerrar votação, reservar).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, forbidden, not_found
from app.models.tables import GroupRow, ParticipantRow

INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 8


def new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def token_matches(raw: str | None, stored_hash: str) -> bool:
    return bool(raw) and hmac.compare_digest(hash_token(raw), stored_hash)


class Caller:
    """Quem está chamando a API para um grupo: um participante, o organizador ou os dois."""

    def __init__(self, group: GroupRow, participant: ParticipantRow | None, is_organizer: bool):
        self.group, self.participant, self.is_organizer = group, participant, is_organizer

    def require_participant(self) -> ParticipantRow:
        if self.participant is None:
            raise AppError(401, "nao_autenticado", "Entre no encontro com seu apelido para fazer isso.")
        return self.participant

    def require_organizer(self) -> None:
        if not self.is_organizer:
            raise forbidden("Só quem organizou o encontro pode fazer isso.")


def participant_by_token(db: Session, raw: str | None) -> ParticipantRow | None:
    if not raw:
        return None
    return db.scalar(select(ParticipantRow).where(ParticipantRow.token_hash == hash_token(raw)))


def load_caller(db: Session, group_id: uuid.UUID, participant_token: str | None,
                organizer_token: str | None) -> Caller:
    group = db.get(GroupRow, group_id)
    if group is None:
        raise not_found("Encontro")
    participant = participant_by_token(db, participant_token)
    if participant is not None and participant.group_id != group.id:
        participant = None  # token válido, mas de outro grupo: não dá acesso a este
    is_org = token_matches(organizer_token, group.organizer_token_hash)
    if participant is None and not is_org:
        raise AppError(401, "nao_autenticado", "Entre no encontro pelo link de convite para ver esta página.")
    return Caller(group, participant, is_org)


def group_caller(group_id: uuid.UUID,
                 x_participant_token: str | None = Header(default=None),
                 x_organizer_token: str | None = Header(default=None),
                 db: Session = Depends(get_db)) -> Caller:
    return load_caller(db, group_id, x_participant_token, x_organizer_token)


def current_participant(x_participant_token: str | None = Header(default=None),
                        db: Session = Depends(get_db)) -> ParticipantRow:
    p = participant_by_token(db, x_participant_token)
    if p is None:
        raise AppError(401, "nao_autenticado", "Sessão de participante inválida ou ausente.")
    return p
