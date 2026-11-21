"""Orquestra o Match: lê o banco, chama o motor (matching.py) e a IA (ai_service.py) e grava a rodada."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models.tables import GroupRow, ParticipantRow, RecommendationRow, RestaurantRow
from app.reference import DATA_DIR, NEIGHBORHOODS
from app.services import ai_service, matching
from app.services.events import log_event, log_once
from app.services.state_machine import transition

MIN_FOR_FORCED_MATCH = 2

_catalog_cache: list[matching.Restaurant] | None = None


# ------------------------------------------------------------------- catálogo

def seed_restaurants(db: Session) -> int:
    """Carrega data/restaurants_seed.json se a tabela estiver vazia (dev e testes; em produção, migration 002)."""
    if db.scalar(select(RestaurantRow.id).limit(1)) is not None:
        return 0
    seed = json.loads((DATA_DIR / "restaurants_seed.json").read_text(encoding="utf-8"))
    for r in seed:
        db.add(RestaurantRow(
            id=uuid.UUID(r["id"]), slug=r["slug"], name=r["name"], cuisine_type=r["cuisine"],
            description=r["description"], neighborhood=r["neighborhood"], city=r["city"], latitude=r["latitude"],
            longitude=r["longitude"], avg_price=r["avg_price"], dietary_options=r["dietary_options"],
            capacity=r["capacity"], ambiences=r["ambiences"], opening_hours=r["opening_hours"],
            availability_rate=r["availability_rate"], rating=r["rating"], rating_count=r["rating_count"],
            simulated_benefit=r["simulated_benefit"], accepts_reservation=r["accepts_reservation"],
            is_fictional=r["is_fictional"]))
    db.commit()
    return len(seed)


def to_engine_restaurant(row: RestaurantRow) -> matching.Restaurant:
    return matching.Restaurant(
        id=str(row.id), name=row.name, cuisine=row.cuisine_type, neighborhood=row.neighborhood,
        latitude=row.latitude, longitude=row.longitude, avg_price=float(row.avg_price),
        dietary_options=frozenset(row.dietary_options), capacity=row.capacity, ambiences=frozenset(row.ambiences),
        opening_hours=row.opening_hours, availability_rate=row.availability_rate, rating=row.rating,
        accepts_reservation=row.accepts_reservation, description=row.description,
        simulated_benefit=row.simulated_benefit)


def catalog(db: Session) -> list[matching.Restaurant]:
    global _catalog_cache
    if _catalog_cache is None:
        rows = db.scalars(select(RestaurantRow).order_by(RestaurantRow.name)).all()
        _catalog_cache = [to_engine_restaurant(r) for r in rows]
    return _catalog_cache


def reset_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


# --------------------------------------------------------- estado do grupo

def with_preferences(group: GroupRow) -> list[ParticipantRow]:
    return [p for p in group.participants if p.preferences is not None]


def missing_preferences(group: GroupRow) -> list[ParticipantRow]:
    return [p for p in group.participants if p.preferences is None]


def is_complete(group: GroupRow) -> bool:
    """Grupo completo: entrou a quantidade de pessoas prevista e todas responderam."""
    return len(group.participants) >= group.party_size and not missing_preferences(group)


def refresh_collect_status(db: Session, group: GroupRow) -> None:
    """Enquanto não há votação aberta, o status reflete se o grupo está completo."""
    if group.status not in ("coletando_preferencias", "match_disponivel"):
        return
    if is_complete(group):
        transition(group, "match_disponivel")
        log_once(db, "preferences_completed", group, participants=len(group.participants))
    else:
        transition(group, "coletando_preferencias")


def invalidate_round(db: Session, group: GroupRow, reason: str) -> bool:
    """Mudança depois do Match: invalida o ranking e os votos da rodada e volta para a coleta."""
    active = db.scalars(select(RecommendationRow).where(RecommendationRow.group_id == group.id,
                                                        RecommendationRow.is_active.is_(True))).all()
    had_match = bool(active) or group.status == "votacao_aberta" or group.match_summary is not None
    if not had_match:
        return False
    for rec in active:
        rec.is_active = False
    if group.status == "votacao_aberta":
        transition(group, "match_disponivel" if is_complete(group) else "coletando_preferencias")
    group.match_summary = None
    log_event(db, "round_invalidated", group, round_number=group.current_round, reason=reason)
    refresh_collect_status(db, group)
    return True


# --------------------------------------------------------------------- Match

def engine_prefs(group: GroupRow, p: ParticipantRow) -> matching.ParticipantPrefs:
    pref = p.preferences
    hood = p.location or group.neighborhood
    c = NEIGHBORHOODS.get(hood) or NEIGHBORHOODS[group.neighborhood]
    return matching.ParticipantPrefs(
        id=str(p.id), nickname=p.nickname, latitude=c["lat"], longitude=c["lng"], origin_neighborhood=hood,
        cuisines=tuple(pref.cuisines), dietary_restrictions=tuple(pref.dietary_restrictions),
        ambiences=tuple(pref.ambience), max_distance_km=float(pref.max_distance),
        max_budget=float(pref.max_budget) if pref.max_budget is not None else None)


def group_context(group: GroupRow) -> matching.GroupContext:
    return matching.GroupContext(budget_per_person=float(group.budget_per_person), party_size=group.party_size,
                                 event_date=group.event_date, event_time=group.event_time)


def generate_match(db: Session, group: GroupRow, *, force: bool, by_organizer: bool,
                   actor_id=None) -> MatchOutcome:
    answered = with_preferences(group)
    missing = missing_preferences(group)
    if group.status == "votacao_aberta":
        raise AppError(409, "match_ja_gerado", "Já existe uma votação aberta para esta rodada.")
    if group.status not in ("coletando_preferencias", "match_disponivel"):
        raise AppError(409, "etapa_invalida", "A escolha deste encontro já foi concluída.")
    if group.status == "coletando_preferencias":
        if not force:
            names = [p.nickname for p in missing]
            pending = len(group.participants) < group.party_size
            raise AppError(409, "grupo_incompleto",
                           "O Match fica disponível quando todos responderem."
                           + (f" Ainda faltam: {', '.join(names)}." if names else "")
                           + (f" Entraram {len(group.participants)} de {group.party_size} pessoas." if pending else ""),
                           {"missing": names, "joined": len(group.participants), "party_size": group.party_size})
        if not by_organizer:
            raise AppError(403, "sem_permissao", "Só quem organizou pode gerar o Match antes de todos responderem.")
        if len(answered) < MIN_FOR_FORCED_MATCH:
            raise AppError(409, "poucas_respostas",
                           f"É preciso pelo menos {MIN_FOR_FORCED_MATCH} pessoas com preferências para gerar o Match.")

    prefs = [engine_prefs(group, p) for p in answered]
    ctx = group_context(group)
    restaurants = catalog(db)
    result = matching.run_match(restaurants, prefs, ctx)

    round_number = group.current_round + 1
    group.current_round = round_number
    summary = {
        "round_number": round_number,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "eligible_count": result.eligible_count,
        "total_restaurants": result.total_restaurants,
        "eliminated_by": result.eliminated_by,
        "effective_budget": result.effective_budget,
        "budget_source": result.budget_source,
        "group_size": result.group_size,
        "required_diets": result.required_diets,
        "suggestions": result.suggestions,
        "conflict_message": result.conflict_message,
        "forced": bool(force and missing),
        "participants_included": [p.nickname for p in answered],
        "participants_missing": [p.nickname for p in missing],
        "explanation_source": None,
    }

    if not result.recommendations:
        group.match_summary = summary
        log_event(db, "match_generated", group, actor_id, round_number=round_number, eligible=0, forced=summary["forced"])
        db.flush()
        return MatchOutcome(group, [], summary)

    context = {
        "data": group.event_date.isoformat(), "horario": group.event_time, "tamanho_do_grupo": result.group_size,
        "teto_de_preco": result.effective_budget, "quem_define_o_teto": result.budget_source,
        "restricoes_obrigatorias": result.required_diets,
        "participantes": [{"apelido": p.nickname, "culinarias_favoritas": list(p.cuisines),
                           "restricoes": list(p.dietary_restrictions), "ambientes": list(p.ambiences),
                           "bairro_de_saida": p.origin_neighborhood, "distancia_maxima_km": p.max_distance_km}
                          for p in prefs],
    }
    explanations, ai = ai_service.explain_recommendations(result.recommendations, context,
                                                          [r.name for r in restaurants])
    summary["explanation_source"] = ai.source
    log_event(db, "ai_call", group, actor_id, function="explicacao", source=ai.source, error=ai.error,
              latency_ms=ai.latency_ms, cached=ai.data.get("cached", False), model=settings.anthropic_model)

    rows = []
    for rec in result.recommendations:
        text, source = explanations[rec.restaurant.id]
        row = RecommendationRow(
            group_id=group.id, restaurant_id=uuid.UUID(rec.restaurant.id), round_number=round_number,
            rank=rec.rank, score=rec.score, mean_score=rec.mean_score, penalty=rec.penalty,
            breakdown=[vars(b) for b in rec.breakdown], highlights=rec.highlights,
            attention_point=rec.attention_point, avg_distance_km=rec.avg_distance_km,
            reason=text, reason_source=source, is_active=True)
        db.add(row)
        rows.append(row)
    group.match_summary = summary
    transition(group, "votacao_aberta")
    log_event(db, "match_generated", group, actor_id, round_number=round_number,
              eligible=result.eligible_count, forced=summary["forced"])
    db.flush()
    return MatchOutcome(group, rows, summary)


class MatchOutcome:
    def __init__(self, group: GroupRow, rows: list[RecommendationRow], summary: dict):
        self.group, self.rows, self.summary = group, rows, summary
