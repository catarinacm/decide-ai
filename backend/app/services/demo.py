"""Grupo de demonstração: quatro participantes fictícios de perfis diferentes, pronto para gerar o Match.

Cada clique em "Ver demonstração" cria um grupo novo, para que avaliadores diferentes não votem no mesmo
grupo ao mesmo tempo (D-013).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.tables import GroupRow, ParticipantRow, PreferenceRow
from app.schemas import today_sp
from app.services.auth import new_invite_code, new_token
from app.services.events import log_event
from app.services.match_service import refresh_collect_status

DEMO_PEOPLE = [
    {"nickname": "Ana", "organizer": True, "location": "Pinheiros",
     "free_text": "Sou vegetariana, curto italiana ou japonesa e prefiro um lugar tranquilo para conversar.",
     "cuisines": ["italiana", "japonesa"], "dietary_restrictions": ["vegetariana"],
     "ambience": ["tranquilo", "casual"], "max_distance": 8, "max_budget": None},
    {"nickname": "Bruno", "organizer": False, "location": "Vila Mariana",
     "free_text": "Estou com o orçamento apertado, no máximo 60 reais. Topo comida brasileira ou hambúrguer.",
     "cuisines": ["brasileira", "hamburgueria"], "dietary_restrictions": [],
     "ambience": ["casual"], "max_distance": 10, "max_budget": 60},
    {"nickname": "Carla", "organizer": False, "location": "Santana",
     "free_text": "Moro longe, em Santana. Gosto de japonesa e mexicana, lugar animado.",
     "cuisines": ["japonesa", "mexicana"], "dietary_restrictions": [],
     "ambience": ["animado"], "max_distance": 12, "max_budget": None},
    {"nickname": "Davi", "organizer": False, "location": "Butantã",
     "free_text": "Não posso comer glúten. Gosto de pizza e comida brasileira, de preferência ao ar livre.",
     "cuisines": ["brasileira", "pizzaria"], "dietary_restrictions": ["sem_gluten"],
     "ambience": ["ao_ar_livre"], "max_distance": 10, "max_budget": None},
]


def next_saturday(today: date) -> date:
    days = (5 - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def create_demo_group(db: Session) -> dict:
    org_raw, org_hash = new_token()
    group = GroupRow(invite_code=new_invite_code(), name="Jantar de sábado (demonstração)", occasion="jantar_amigos",
                     event_date=next_saturday(today_sp()), event_time="20:00", budget_per_person=100, party_size=4,
                     neighborhood="Pinheiros", organizer_token_hash=org_hash, is_demo=True)
    db.add(group)
    db.flush()
    log_event(db, "group_created", group, demo=True)
    identities = []
    for person in DEMO_PEOPLE:
        raw, h = new_token()
        p = ParticipantRow(group_id=group.id, nickname=person["nickname"], nickname_key=person["nickname"].lower(),
                           location=person["location"], is_organizer=person["organizer"], is_simulated=True,
                           token_hash=h)
        p.preferences = PreferenceRow(cuisines=person["cuisines"], dietary_restrictions=person["dietary_restrictions"],
                                      ambience=person["ambience"], max_distance=person["max_distance"],
                                      max_budget=person["max_budget"], free_text=person["free_text"])
        group.participants.append(p)
        db.flush()
        log_event(db, "participant_joined", group, p.id, simulated=True)
        identities.append({"participant_id": str(p.id), "token": raw, "nickname": p.nickname,
                           "is_organizer": person["organizer"]})
    refresh_collect_status(db, group)
    db.flush()
    return {"group": group, "organizer_token": org_raw, "identities": identities}
