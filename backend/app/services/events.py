"""Instrumentação do funil. Eventos são dados de uso do protótipo, nunca conversões reais."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import EventRow, GroupRow

FUNNEL = [
    ("group_created", "Grupo criado"),
    ("preferences_completed", "Preferências completas"),
    ("recommendations_viewed", "Recomendações vistas"),
    ("choice_completed", "Escolha concluída"),
    ("reservation_simulated", "Reserva simulada"),
]


def log_event(db: Session, name: str, group: GroupRow | None = None, participant_id: uuid.UUID | None = None,
              **properties) -> EventRow:
    ev = EventRow(name=name, group_id=group.id if group else None, participant_id=participant_id,
                  properties=properties, is_demo=bool(group and group.is_demo))
    db.add(ev)
    db.flush()
    return ev


def log_once(db: Session, name: str, group: GroupRow, participant_id: uuid.UUID | None = None, **properties) -> bool:
    """Registra o evento só se ainda não existir para este grupo (e participante, se informado)."""
    q = select(EventRow.id).where(EventRow.name == name, EventRow.group_id == group.id)
    if participant_id is not None:
        q = q.where(EventRow.participant_id == participant_id)
    if "round_number" in properties:
        # O JSON é comparado no Python para funcionar igual em SQLite e Postgres.
        rows = db.scalars(select(EventRow).where(EventRow.name == name, EventRow.group_id == group.id,
                                                 EventRow.participant_id == participant_id)).all()
        if any(r.properties.get("round_number") == properties["round_number"] for r in rows):
            return False
    elif db.scalar(q.limit(1)) is not None:
        return False
    log_event(db, name, group, participant_id, **properties)
    return True
