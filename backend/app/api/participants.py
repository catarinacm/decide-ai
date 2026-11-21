"""Preferências individuais. Cada participante só altera as próprias."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import preferences_out
from app.database import get_db
from app.errors import conflict, forbidden
from app.models.tables import GroupRow, ParticipantRow, PreferenceRow
from app.schemas import PreferencesIn
from app.services.auth import current_participant
from app.services.events import log_event
from app.services.match_service import invalidate_round, refresh_collect_status
from app.services.state_machine import OPEN_STATES

router = APIRouter(tags=["participantes"])


def _rule_fields(location, cuisines, diets, ambiences, max_distance, max_budget) -> tuple:
    return (location, tuple(sorted(cuisines)), tuple(sorted(diets)), tuple(sorted(ambiences)), float(max_distance),
            None if max_budget is None else float(max_budget))


@router.get("/participants/me")
def me(participant: ParticipantRow = Depends(current_participant)):
    return {"participant_id": str(participant.id), "group_id": str(participant.group_id),
            "nickname": participant.nickname, "is_organizer": participant.is_organizer,
            "preferences": preferences_out(participant)}


@router.put("/participants/{participant_id}/preferences")
def save_preferences(participant_id: uuid.UUID, body: PreferencesIn,
                     participant: ParticipantRow = Depends(current_participant), db: Session = Depends(get_db)):
    if participant.id != participant_id:
        raise forbidden("Você só pode alterar as suas próprias preferências.")
    group: GroupRow = participant.group
    if group.status not in OPEN_STATES:
        raise conflict("encontro_fechado", "A escolha já foi concluída; as preferências não podem mais mudar.")

    pref = participant.preferences
    first_time = pref is None
    values = dict(cuisines=body.cuisines, dietary_restrictions=body.dietary_restrictions, ambience=body.ambiences,
                  max_distance=body.max_distance_km, max_budget=body.max_budget,
                  additional_preferences=body.additional_preferences, free_text=body.free_text,
                  parsed_by=body.parsed_by)
    # Só os campos estruturados entram nas regras; mudar só o texto livre não invalida a rodada.
    old_rules = None if first_time else _rule_fields(participant.location, pref.cuisines, pref.dietary_restrictions,
                                                     pref.ambience, pref.max_distance, pref.max_budget)
    new_rules = _rule_fields(body.origin_neighborhood, body.cuisines, body.dietary_restrictions, body.ambiences,
                             body.max_distance_km, body.max_budget)
    changed = old_rules != new_rules
    if first_time:
        participant.preferences = PreferenceRow(**values)
    else:
        for k, v in values.items():
            setattr(pref, k, v)
    participant.location = body.origin_neighborhood
    db.flush()

    invalidated = False
    if changed:
        # Regra de negócio: mudar preferência depois do Match invalida ranking e votos e abre nova rodada.
        invalidated = invalidate_round(db, group, reason="preferencias_alteradas")
    refresh_collect_status(db, group)
    log_event(db, "preferences_saved", group, participant.id, first_time=first_time, parsed_by=body.parsed_by,
              invalidated_round=invalidated)
    db.commit()
    return {"preferences": preferences_out(participant), "group_status": group.status,
            "round_invalidated": invalidated}
