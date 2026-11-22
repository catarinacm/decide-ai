"""Métricas do funil, calculadas da tabela events, e valores de referência para o frontend."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.errors import AppError
from app.models.tables import EventRow, GroupRow, ReviewRow
from app.reference import AMBIENCES, CUISINES, DIETS, NEIGHBORHOODS, OCCASIONS
from app.services.events import FUNNEL

router = APIRouter(tags=["metricas"])

METRICS_NOTICE = ("Dados de uso deste protótipo, registrados de verdade a cada ação, mas gerados por testes e "
                  "demonstrações. Não são conversões reais nem resultados de negócio.")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Métricas são internas: só quem tem a ADMIN_TOKEN (a dona do produto) vê."""
    if not settings.admin_token or not x_admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
        raise AppError(403, "acesso_restrito", "Área restrita. Informe a chave de acesso às métricas.")


@router.get("/metrics", dependencies=[Depends(require_admin)])
def metrics(include_demo: bool = False, db: Session = Depends(get_db)):
    q = select(EventRow)
    if not include_demo:
        q = q.where(EventRow.is_demo.is_(False))
    events = db.scalars(q).all()

    groups_by_step = {name: set() for name, _ in FUNNEL}
    for e in events:
        if e.name in groups_by_step and e.group_id:
            groups_by_step[e.name].add(e.group_id)
    created = len(groups_by_step["group_created"])

    def pct(n: int) -> float | None:
        return round(100 * n / created, 1) if created else None

    funnel = [{"step": name, "label": label, "groups": len(groups_by_step[name]),
               "pct_of_created": pct(len(groups_by_step[name]))} for name, label in FUNNEL]

    decisions = [e.properties.get("seconds_to_decision") for e in events if e.name == "choice_completed"]
    decisions = [d for d in decisions if isinstance(d, (int, float))]
    ties = sum(1 for e in events if e.name == "choice_completed" and e.properties.get("tie"))

    gq = select(GroupRow)
    if not include_demo:
        gq = gq.where(GroupRow.is_demo.is_(False))
    groups = db.scalars(gq).all()
    expected = sum(max(g.party_size, len(g.participants)) for g in groups)
    answered = sum(1 for g in groups for p in g.participants if p.preferences is not None)

    ai_calls = [e for e in events if e.name == "ai_call"]
    rq = select(ReviewRow.rating)
    ratings = list(db.scalars(rq).all())
    invalidations = sum(1 for e in events if e.name == "round_invalidated")

    return {
        "notice": METRICS_NOTICE,
        "include_demo": include_demo,
        "main_metric": {
            "label": "Grupos criados que concluíram a escolha",
            "value_pct": pct(len(groups_by_step["choice_completed"])),
            "numerator": len(groups_by_step["choice_completed"]), "denominator": created,
        },
        "funnel": funnel,
        "avg_minutes_to_decision": round(sum(decisions) / len(decisions) / 60, 1) if decisions else None,
        "decisions_by_tiebreak": ties,
        "participation_rate_pct": round(100 * answered / expected, 1) if expected else None,
        "participants_answered": answered, "participants_expected": expected,
        "rounds_invalidated": invalidations,
        "ai": {
            "calls": len(ai_calls),
            "ia": sum(1 for e in ai_calls if e.properties.get("source") == "ia"),
            "fallback": sum(1 for e in ai_calls if e.properties.get("source") == "fallback"),
        },
        "reviews": {"count": len(ratings), "average": round(sum(ratings) / len(ratings), 2) if ratings else None},
    }


@router.get("/meta")
def meta():
    return {
        "cuisines": [{"value": k, "label": v} for k, v in CUISINES.items()],
        "dietary_options": [{"value": k, "label": v} for k, v in DIETS.items()],
        "ambiences": [{"value": k, "label": v} for k, v in AMBIENCES.items()],
        "occasions": [{"value": k, "label": v} for k, v in OCCASIONS.items()],
        "neighborhoods": sorted(NEIGHBORHOODS),
        "ai_enabled": settings.ai_enabled,
    }
